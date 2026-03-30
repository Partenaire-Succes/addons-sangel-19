import logging

from odoo import fields, models, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SageX3SendWizard(models.TransientModel):
    """
    Wizard d'envoi vers SAGE X3.

    Lance 2 flux en séquence :
      1. Récap journalier POS (ENCAI + DECAI)
         → inclut automatiquement les account.payment du jour dans l'ENCAI
      2. Factures et avoirs classiques hors POS (FACLI / AVCLI)

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
    count_invoices = fields.Integer(
        string  = "Factures: FACLI",
        compute = "_compute_counts",
    )
    count_refunds = fields.Integer(
        string  = "Avoirs: AVCLI",
        compute = "_compute_counts",
    )
    count_payments = fields.Integer(
        string  = "Règlements: ENCAI",
        compute = "_compute_counts",
        help    = "Ces règlements seront inclus dans le récap ENCAI journalier, "
                  "pas envoyés séparément.",
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
                wizard.count_invoices     = 0
                wizard.count_refunds      = 0
                wizard.count_payments     = 0
                continue

            company_ids = wizard.company_ids.ids

            # Sessions POS fermées avec paiements non envoyés
            wizard.count_pos_sessions = self.env['pos.session'].search_count([
                ('company_id', 'in', company_ids),
                ('state',      '=',  'closed'),
                ('sage_x3_sent', '=',  False),
                ('start_at',   '>=', wizard.date_from),
                ('start_at',   '<=', wizard.date_to),
            ])

            # Factures classiques hors POS
            wizard.count_invoices = self.env['account.move'].search_count([
                ('move_type',     '=',  'out_invoice'),
                ('state',         '=',  'posted'),
                ('sage_x3_sent',  '=',  False),
                ('pos_order_ids', '=',  False),
                ('company_id',    'in', company_ids),
                ('invoice_date',  '>=', wizard.date_from),
                ('invoice_date',  '<=', wizard.date_to),
            ])

            # Avoirs classiques hors POS
            wizard.count_refunds = self.env['account.move'].search_count([
                ('move_type',     '=',  'out_refund'),
                ('state',         '=',  'posted'),
                ('sage_x3_sent',  '=',  False),
                ('pos_order_ids', '=',  False),
                ('company_id',    'in', company_ids),
                ('invoice_date',  '>=', wizard.date_from),
                ('invoice_date',  '<=', wizard.date_to),
            ])

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

    # =========================================================================
    # ACTION PRINCIPALE
    # =========================================================================

    def action_confirm_send(self):
        """
        Lance les envois dans cet ordre :
          1. Récap journalier POS → ENCAI (ventes + règlements) + DECAI
          2. Factures classiques hors POS → FACLI
          3. Avoirs classiques hors POS   → AVCLI

        Les account.payment sont inclus dans l'ENCAI du flux POS (étape 1).
        Ils ne sont jamais envoyés séparément pour éviter les doublons.
        """
        self.ensure_one()

        company_ids    = self.company_ids.ids
        account_model  = self.env['account.move']

        # Factures et avoirs classiques hors POS (les deux types ensemble)
        pending_invoices_and_refunds = account_model.search([
            ('move_type',     'in', ['out_invoice', 'out_refund']),
            ('state',         '=',  'posted'),
            ('sage_x3_sent',  '=',  False),
            ('pos_order_ids', '=',  False),
            ('sage_sent',     '=',  True),
            ('company_id',    'in', company_ids),
            ('invoice_date',  '>=', self.date_from),
            ('invoice_date',  '<=', self.date_to),
        ])

        _logger.info(
            "📤 Envoi SAGE X3 | Sociétés: %s | Période: %s → %s | "
            "Factures/Avoirs: %s",
            self.company_ids.mapped('name'),
            self.date_from,
            self.date_to,
            len(pending_invoices_and_refunds),
        )

        # ── Flux 1 : Récap journalier POS (ENCAI + DECAI) ────────────────────
        # Inclut automatiquement les account.payment du jour dans l'ENCAI
        result_pos = account_model._process_bulk_send_to_sage_x3(
            self.date_from, self.date_to, company_ids
        )

        # ── Flux 2 : Factures et avoirs classiques (FACLI / AVCLI) ───────────
        result_invoices = account_model._process_bulk_send_classic_invoices_to_sage_x3(
            pending_invoices_and_refunds.ids
        )

        # ── Résumé ────────────────────────────────────────────────────────────
        total_success = result_pos['success'] + result_invoices['success']
        total_errors  = result_pos['errors']  + result_invoices['errors']

        if total_errors == 0:
            title      = "✅ Envoi terminé avec succès"
            notif_type = "success"
            message    = (
                f"Toutes les données ont été envoyées.\n"
                f"• Récap caisse POS  : {result_pos['success']} journée(s)\n"
                f"• Factures / Avoirs : {result_invoices['success']}"
            )
        else:
            title      = "⚠️ Envoi terminé avec erreurs"
            notif_type = "warning"
            message    = (
                f"Récap caisse POS  : {result_pos['success']} succès "
                f"/ {result_pos['errors']} erreur(s)\n"
                f"Factures / Avoirs : {result_invoices['success']} succès "
                f"/ {result_invoices['errors']} erreur(s)"
            )
            # Logger le détail des erreurs
            for err in result_pos['error_details'] + result_invoices['error_details']:
                _logger.error("❌ %s", err)

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   title,
                'message': message,
                'type':    notif_type,
                'sticky':  True,
                'next':    None,  # <-- plus d'erreur
            },
        }