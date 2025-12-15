from odoo import models, fields, api, _
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError


class ProductPriceHistoryWizard(models.TransientModel):
    _name = 'product.price.history.wizard'
    _description = "Assistant de création de rapport de l'historique des prix"

    period_type = fields.Selection([
        ('daily', 'Quotidien'),
        ('weekly', 'Hebdomadaire'),
        ('biweekly', 'Quinzaine'),
        ('monthly', 'Mensuel'),
        ('quarterly', 'Trimestriel'),
        ('semiannual', 'Semestriel'),
        ('yearly', 'Annuel'),
        ('custom', 'Personnalisé')
    ], string='Type de période', required=True, default='monthly')

    date_from = fields.Date(string='Date de début', required=True, default=fields.Date.today)
    date_to = fields.Date(string='Date de fin', required=True, default=fields.Date.today)


    price_history_ids = fields.Many2many(
        'product.price.history',
        string='Historique des prix',
        compute='_compute_price_history_ids'
    )

    @api.depends('period_type', 'date_from', 'date_to')
    def _compute_price_history_ids(self):
        for record in self:
            record.price_history_ids = self.env['product.price.history'].search([
                ('date_changed', '>=', record.date_from),
                ('date_changed', '<=', record.date_to),
            ])

    @api.onchange('period_type', 'date_from')
    def _onchange_dates(self):
        """Met à jour la date_to en fonction du type de période et de la date_from"""
        if not self.date_from:
            return

        if self.period_type == 'daily':
            self.date_to = self.date_from

        elif self.period_type == 'weekly':
            self.date_to = self.date_from + timedelta(days=6)

        elif self.period_type == 'biweekly':
            self.date_to = self.date_from + timedelta(days=13)

        elif self.period_type == 'monthly':
            self.date_to = self.date_from + relativedelta(months=1) - timedelta(days=1)

        elif self.period_type == 'quarterly':
            self.date_to = self.date_from + relativedelta(months=3) - timedelta(days=1)

        elif self.period_type == 'semiannual':
            self.date_to = self.date_from + relativedelta(months=6) - timedelta(days=1)

        elif self.period_type == 'yearly':
            self.date_to = self.date_from + relativedelta(years=1) - timedelta(days=1)

        elif self.period_type == 'custom':
            # Ne calcule rien, l'utilisateur choisit lui-même
            self.date_to = self.date_to or self.date_from


    def action_print(self):
        return self.env.ref('custom_price_change_tracker.action_report_product_price_history').report_action(self)