import logging
from datetime import timedelta

from odoo import fields, models, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SageX3SendWizard(models.TransientModel):
    """
    Wizard d'envoi vers SAGE X3.

    Lance 3 flux en séquence :
      1. Récap journalier POS (ENCAI + DECAI)
         → inclut automatiquement les account.payment du jour dans l'ENCAI
      2. Factures et avoirs classiques hors POS (FACLI / AVCLI) — sélection manuelle
      3. Factures et avoirs liés à des ventes (sale.order) — auto-découverte

    Note : les account.payment ne sont PAS envoyés séparément.
    Ils sont intégrés dans l'ENCAI journalier du flux POS.
    """
    _name        = 'sage.x3.send.wizard'
    _description = 'Wizard envoi SAGE X3'

    date_from = fields.Date(
        string   = "Date début",
        required = True,
        default  = fields.Date.today,
    )
    date_to = fields.Date(
        string   = "Date fin",
        required = True,
        default  = fields.Date.today,
    )
    company_ids = fields.Many2many(
        'res.company',
        string   = "Sociétés",
        required = True,
        default  = lambda self: [(6, 0, self.env.company.ids)],
    )

    # Compteurs affichés dans le formulaire wizard
    count_pos_sessions = fields.Integer(
        string  = "Sessions POS du Jours",
        compute = "_compute_counts",
    )
    count_refunds = fields.Integer(
        string  = "Avoirs POS is_limit: AVCLI",
        compute = "_compute_counts",
    )
    count_payments = fields.Integer(
        string  = "Règlements: ENCAI",
        compute = "_compute_counts",
        help    = "Ces règlements seront inclus dans le récap ENCAI journalier, "
                  "pas envoyés séparément.",
    )
    count_sale_invoices = fields.Integer(
        string  = "Factures ventes: FACLI/AVCLI",
        compute = "_compute_counts",
        help    = "Factures et avoirs clients liés à un bon de commande (sale.order).",
    )

    # =========================================================================
    # CONTRAINTES ET COMPTEURS
    # =========================================================================

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(
                    "La date de début doit être antérieure ou égale à la date de fin."
                )

    @api.depends('date_from', 'date_to', 'company_ids')
    def _compute_counts(self):
        for wizard in self:
            if not wizard.date_from or not wizard.date_to or not wizard.company_ids:
                wizard.count_pos_sessions = 0
                wizard.count_refunds      = 0
                wizard.count_payments     = 0
                wizard.count_sale_invoices     = 0
                continue

            company_ids = wizard.company_ids.ids

            # Sessions POS fermées avec paiements non envoyés
            date_from_dt = fields.Datetime.to_datetime(wizard.date_from)
            date_to_dt   = fields.Datetime.to_datetime(wizard.date_to) + timedelta(days=1)

            pos_sessions = self.env['pos.session'].search([
                ('company_id',   'in', company_ids),
                ('state',        '=',  'closed'),
                ('sage_x3_sent', '=',  False),
                ('start_at',     '>=', date_from_dt),
                ('start_at',     '<',  date_to_dt),
            ])

            wizard.count_pos_sessions = len(pos_sessions.filtered(lambda s: s.cash_register_balance_end > 0))

            # Avoirs POS avec mode de paiement is_limit
            refund_candidates = self.env['account.move'].search([
                ('move_type',    '=',  'out_refund'),
                ('state',        '=',  'posted'),
                ('sage_x3_sent', '=',  False),
                ('company_id',   'in', company_ids),
                ('invoice_date', '>=', wizard.date_from),
                ('invoice_date', '<=', wizard.date_to),
            ])
            wizard.count_refunds = len(refund_candidates.filtered(
                lambda m: any(
                    p.payment_method_id.is_limit
                    for o in m.pos_order_ids
                    for p in o.payment_ids
                )
            ))

            # Règlements clients qui seront inclus dans l'ENCAI (info seulement)
            wizard.count_payments = self.env['account.payment'].search_count([
                ('payment_type', '=',  'inbound'),
                ('partner_type', '=',  'customer'),
                ('state',        '=',  'paid'),
                ('pos_order_id', '=',  False),
                ('partner_id', '!=', False),
                ('sage_x3_sent', '=',  False),
                ('company_id',   'in', company_ids),
                ('date',         '>=', wizard.date_from),
                ('date',         '<=', wizard.date_to),
            ])

            wizard.count_sale_invoices = self.env['account.move'].search_count([
                ('move_type',                      'in', ('out_invoice', 'out_refund')),
                ('state',                          '=',  'posted'),
                ('sage_x3_sent',                   '=',  False),
                ('company_id',                     'in', company_ids),
                ('invoice_date',                   '>=', wizard.date_from),
                ('invoice_date',                   '<=', wizard.date_to),
                ('invoice_line_ids.sale_line_ids', '!=', False),
            ])

    # =========================================================================
    # ACTION PRINCIPALE
    # =========================================================================

    def action_confirm_send(self):
        """
        Lance les envois dans cet ordre :
          1. Récap journalier POS → ENCAI (ventes + règlements) + DECAI
          2. Factures classiques hors POS (FACLI / AVCLI) — sélection manuelle
          3. Factures liées à des ventes (sale.order) → FACLI / AVCLI — auto

        Les account.payment sont inclus dans l'ENCAI du flux POS (étape 1).
        Ils ne sont jamais envoyés séparément pour éviter les doublons.
        """
        self.ensure_one()

        company_ids   = self.company_ids.ids
        account_model = self.env['account.move']

        # Factures et avoirs classiques hors POS (avoirs POS is_limit)
        moves = account_model.search([
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('sage_x3_sent', '=', False),
            ('company_id', 'in', company_ids),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ])
        pending_invoices_refunds = moves.filtered(
            lambda m: any(
                p.payment_method_id.is_limit
                for o in m.pos_order_ids
                for p in o.payment_ids
            )
        )

        _logger.info(
            "📤 Envoi SAGE X3 | Sociétés: %s | Période: %s → %s | "
            "Avoirs POS is_limit: %s",
            self.company_ids.mapped('name'),
            self.date_from,
            self.date_to,
            len(pending_invoices_refunds),
        )

        # ── Flux 1 : Récap journalier POS (ENCAI + DECAI) ────────────────────
        result_pos = account_model._process_bulk_send_to_sage_x3(
            self.date_from, self.date_to, company_ids
        )

        # ── Flux 2 : Avoirs classiques hors POS (sélection manuelle) ─────────
        result_invoices = account_model._process_bulk_send_classic_invoices_to_sage_x3(
            pending_invoices_refunds.ids
        )

        # ── Flux 3 : Factures liées à des ventes (sale.order) ────────────────
        result_sale = account_model._process_bulk_send_sale_invoices_to_sage_x3(
            self.date_from, self.date_to, company_ids
        )

        # ── Résumé ────────────────────────────────────────────────────────────
        total_errors = (
            result_pos['errors'] + result_invoices['errors'] + result_sale['errors']
        )

        if total_errors == 0:
            title      = "✅ Envoi terminé avec succès"
            notif_type = "success"
            message    = (
                f"Toutes les données ont été envoyées.\n"
                f"• Récap caisse POS     : {result_pos['success']} journée(s)\n"
                f"• Avoirs POS classiques: {result_invoices['success']}\n"
                f"• Factures ventes      : {result_sale['success']}"
            )
        else:
            title      = "⚠️ Envoi terminé avec erreurs"
            notif_type = "warning"

            all_errors = (
                result_pos['error_details']
                + result_invoices['error_details']
                + result_sale['error_details']
            )

            detail_lines = []
            for err in all_errors:
                detail_lines.append(f"  • {err}")
                _logger.error("❌ %s", err)

            detail_str = "\n".join(detail_lines) if detail_lines else "Voir les logs serveur."

            message = (
                f"Récap caisse POS     : {result_pos['success']} succès "
                f"/ {result_pos['errors']} erreur(s)\n"
                f"Avoirs POS classiques: {result_invoices['success']} succès "
                f"/ {result_invoices['errors']} erreur(s)\n"
                f"Factures ventes      : {result_sale['success']} succès "
                f"/ {result_sale['errors']} erreur(s)\n"
                f"\nÉcritures non envoyées :\n{detail_str}"
            )

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   title,
                'message': message,
                'type':    notif_type,
                'sticky':  True,
                'next':    None,
            },
        }