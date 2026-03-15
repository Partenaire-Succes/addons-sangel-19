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
        default=fields.Date.today
    )
    date_to = fields.Date(
        string="Date fin",
        required=True,
        default=fields.Date.today
    )
    company_ids = fields.Many2many(
        'res.company',
        string="Sociétés",
        required=True,
        default=lambda self: [(6, 0, self.env.company.ids)]
    )
    count_invoices = fields.Integer(string="Nombre de factures à envoyer", compute="_compute_counts")
    count_payments = fields.Integer(string="Nombre de paiements à envoyer", compute="_compute_counts")

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError("La date de début doit être antérieure à la date de fin")

    @api.depends('date_from', 'date_to', 'company_ids')
    def _compute_counts(self):
        for wizard in self:
            if not wizard.date_from or not wizard.date_to or not wizard.company_ids:
                wizard.count_invoices = 0
                wizard.count_payments = 0
                continue

            company_ids = wizard.company_ids.ids

            wizard.count_payments = self.env['account.payment'].search_count([
                ('payment_type', '=', 'inbound'),
                ('partner_type', '=', 'customer'),
                ('state', '=', 'paid'),
                ('sage_x3_sent', '=', False),
                ('company_id', 'in', company_ids),
                ('date', '>=', wizard.date_from),
                ('date', '<=', wizard.date_to),
            ])

            wizard.count_invoices = self.env['account.move'].search_count([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('sage_x3_sent', '=', False),
                ('pos_order_ids', '=', False),
                ('company_id', 'in', company_ids),
                ('invoice_date', '>=', wizard.date_from),
                ('invoice_date', '<=', wizard.date_to),
            ])

    def action_confirm_send(self):
        """Confirme et lance l'envoi"""
        self.ensure_one()

        account = self.env['account.move']
        payment = self.env['account.payment']
        company = self.env.company

        pending_payments = payment.search([
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state', '=', 'paid'),
            ('pos_payment_method_id', '=', False),
            ('pos_session_id', '=', False),
            ('sage_x3_sent', '=', False),
            ('company_id', '=', company.id),
            ('date', '>=', self.date_from),         # ✅ Ajout filtre date
            ('date', '<=', self.date_to),           # ✅ Ajout filtre date
        ])

        pending_invoices = account.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('sage_x3_sent', '=', False),
            ('pos_order_ids', '=', False),
            ('company_id', '=', company.id),
            ('invoice_date', '>=', self.date_from), # ✅ Ajout filtre date
            ('invoice_date', '<=', self.date_to),   # ✅ Ajout filtre date
        ])

        # Lancer les envois
        result_pos      = account._process_bulk_send_to_sage_x3(self.date_from, self.date_to, self.company_ids.ids)
        result_sale     = account._process_bulk_send_classic_invoices_to_sage_x3(pending_invoices.ids)
        result_payments = payment._process_bulk_send_payments_to_sage_x3(pending_payments.ids)

        # ✅ Calcul unique
        total_errors = result_pos['errors'] + result_sale['errors'] + result_payments['errors']

        if total_errors == 0:
            message = "Toutes les données ont été envoyées avec succès."
        else:
            message = (
                f"{result_pos['errors']} erreur(s) pour les ventes au comptant, "
                f"{result_sale['errors']} erreur(s) pour les factures classiques, "
                f"{result_payments['errors']} erreur(s) pour les paiements."
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Envoi terminé' if total_errors == 0 else '⚠️ Envoi terminé avec erreurs',
                'message': message,
                'type': 'success' if total_errors == 0 else 'warning',
                'sticky': True,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                },
            }
        }