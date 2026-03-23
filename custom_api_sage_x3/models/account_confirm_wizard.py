from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class SageX3SendWizard(models.TransientModel):
    _name = 'sage.x3.send.wizard'
    _description = 'Wizard envoi SAGE X3'

    date_from = fields.Date(
        string="Date début",
        required=True,
        default=fields.Date.today,
    )
    date_to = fields.Date(
        string="Date fin",
        required=True,
        default=fields.Date.today,
    )
    company_ids = fields.Many2many(
        'res.company',
        string="Sociétés",
        required=True,
        default=lambda self: [(6, 0, self.env.company.ids)],
    )
    count_invoices = fields.Integer(
        string="Factures à envoyer",
        compute="_compute_counts",
    )
    count_payments = fields.Integer(
        string="Paiements à envoyer",
        compute="_compute_counts",
    )
    count_pos_sessions = fields.Integer(
        string="Sessions POS à envoyer",
        compute="_compute_counts",
    )

    # -------------------------------------------------------------------------
    # Contraintes
    # -------------------------------------------------------------------------

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(
                    "La date de début doit être antérieure ou égale à la date de fin."
                )

    # -------------------------------------------------------------------------
    # Compteurs (informatifs)
    # -------------------------------------------------------------------------

    @api.depends('date_from', 'date_to', 'company_ids')
    def _compute_counts(self):
        for wizard in self:
            if not wizard.date_from or not wizard.date_to or not wizard.company_ids:
                wizard.count_invoices = 0
                wizard.count_payments = 0
                wizard.count_pos_sessions = 0
                continue

            company_ids = wizard.company_ids.ids

            # Factures classiques (hors POS)
            wizard.count_invoices = self.env['account.move'].search_count([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('sage_x3_sent', '=', False),
                ('pos_order_ids', '=', False),
                ('company_id', 'in', company_ids),
                ('invoice_date', '>=', wizard.date_from),
                ('invoice_date', '<=', wizard.date_to),
            ])

            # Paiements clients (hors POS)
            wizard.count_payments = self.env['account.payment'].search_count([
                ('payment_type', '=', 'inbound'),
                ('partner_type', '=', 'customer'),
                ('state', '=', 'paid'),
                ('sage_x3_sent', '=', False),
                ('pos_payment_method_id', '=', False),
                ('pos_session_id', '=', False),
                ('company_id', 'in', company_ids),
                ('date', '>=', wizard.date_from),
                ('date', '<=', wizard.date_to),
            ])

            # Sessions POS clôturées non envoyées
            wizard.count_pos_sessions = self.env['pos.session'].search_count([
                ('company_id', 'in', company_ids),
                ('state', '=', 'closed'),
                ('start_at', '>=', str(wizard.date_from)),
                ('start_at', '<=', str(wizard.date_to) + ' 23:59:59'),
            ])

    # -------------------------------------------------------------------------
    # Action principale
    # -------------------------------------------------------------------------

    def action_confirm_send(self):
        """Lance l'envoi pour toutes les sociétés sélectionnées."""
        self.ensure_one()

        account = self.env['account.move']
        payment = self.env['account.payment']

        # CORRECTION : utiliser company_ids (multi-société), pas env.company
        company_ids = self.company_ids.ids

        # Factures classiques (hors POS) — TOUTES les sociétés sélectionnées
        pending_invoices = account.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('sage_x3_sent', '=', False),
            ('pos_order_ids', '=', False),
            ('company_id', 'in', company_ids),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ])

        # Paiements clients (hors POS) — TOUTES les sociétés sélectionnées
        pending_payments = payment.search([
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state', '=', 'paid'),
            ('sage_x3_sent', '=', False),
            ('pos_payment_method_id', '=', False),
            ('pos_session_id', '=', False),
            ('company_id', 'in', company_ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])

        # --- Lancement des envois ---
        result_pos = account._process_bulk_send_to_sage_x3(
            self.date_from, self.date_to, company_ids
        )
        result_sale = account._process_bulk_send_classic_invoices_to_sage_x3(
            pending_invoices.ids
        )
        result_payments = payment._process_bulk_send_payments_to_sage_x3(
            pending_payments.ids
        )

        # --- Résumé ---
        total_success = result_pos['success'] + result_sale['success'] + result_payments['success']
        total_errors = result_pos['errors'] + result_sale['errors'] + result_payments['errors']

        if total_errors == 0:
            title = '✅ Envoi terminé'
            message = (
                f"Toutes les données ont été envoyées avec succès.\n"
                f"• Récaps POS : {result_pos['success']}\n"
                f"• Factures classiques : {result_sale['success']}\n"
                f"• Paiements : {result_payments['success']}"
            )
            notif_type = 'success'
        else:
            title = '⚠️ Envoi terminé avec erreurs'
            lines = [
                f"• Récaps POS : {result_pos['success']} succès / {result_pos['errors']} erreur(s)",
                f"• Factures classiques : {result_sale['success']} succès / {result_sale['errors']} erreur(s)",
                f"• Paiements : {result_payments['success']} succès / {result_payments['errors']} erreur(s)",
            ]

            # Détail des 5 premières erreurs
            all_errors = (
                result_pos['error_details']
                + result_sale['error_details']
                + result_payments['error_details']
            )
            if all_errors:
                lines.append("\nDétail des erreurs (5 premières) :")
                lines += [f"  - {e}" for e in all_errors[:5]]

            message = '\n'.join(lines)
            notif_type = 'warning'

        # Journaliser le résumé complet
        _logger.info(
            "📊 Envoi SAGE X3 terminé — %s succès / %s erreur(s)",
            total_success, total_errors
        )
        if total_errors > 0:
            all_errors = (
                result_pos['error_details']
                + result_sale['error_details']
                + result_payments['error_details']
            )
            for err in all_errors:
                _logger.error("   ❌ %s", err)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notif_type,
                'sticky': True,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
