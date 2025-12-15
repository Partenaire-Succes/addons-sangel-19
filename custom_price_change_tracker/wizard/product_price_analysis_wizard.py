from odoo import models, fields, api, _
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError


class ProductPriceAnalysisWizard(models.TransientModel):
    _name = 'product.price.analysis.wizard'
    _description = "Assistant d'analyse des prix produits"

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

    date_from = fields.Date(
        string='Date de début',
        required=True,
        default=fields.Date.today
    )

    date_to = fields.Date(
        string='Date de fin',
        required=True,
        default=fields.Date.today
    )

    product_ids = fields.Many2many(
        comodel_name='product.template',
        string='Produits',
        help='Laisser vide pour tous les produits'
    )

    category_ids = fields.Many2many(
        comodel_name='product.category',
        string='Catégories',
        help='Filtrer par catégorie de produits'
    )

    price_history_ids = fields.Many2many(
        'product.price.history',
        string='Historique des prix',
        compute='_compute_price_history_ids'
    )

    @api.depends('period_type', 'date_from', 'date_to', 'product_ids', 'category_ids')
    def _compute_price_history_ids(self):
        for record in self:
            domain = [
                ('date_changed', '>=', fields.Datetime.to_datetime(record.date_from)),
                ('date_changed', '<=',
                 fields.Datetime.to_datetime(record.date_to).replace(hour=23, minute=59, second=59))
            ]

            if record.product_ids:
                domain.append(('product_id', 'in', record.product_ids.ids))

            if record.category_ids:
                products = self.env['product.template'].search([
                    ('categ_id', 'child_of', record.category_ids.ids)
                ])
                domain.append(('product_id', 'in', products.ids))

            record.price_history_ids = self.env['product.price.history'].search(domain)

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
        """Générer le rapport PDF et fermer le wizard"""
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_('La date de début doit être antérieure à la date de fin.'))

        # 1️⃣ Lancer le rapport PDF
        report_action = self.env.ref(
            'custom_price_change_tracker.action_report_product_price_analysis'
        ).report_action(self)

        # 2️⃣ Ajouter l'action de fermeture
        report_action['close_on_report_download'] = True

        return report_action

    def _get_report_data(self):
        """Récupérer les données pour le rapport"""
        self.ensure_one()

        domain = [
            ('date_changed', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('date_changed', '<=', fields.Datetime.to_datetime(self.date_to).replace(hour=23, minute=59, second=59))
        ]

        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))

        if self.category_ids:
            products = self.env['product.template'].search([
                ('categ_id', 'child_of', self.category_ids.ids)
            ])
            domain.append(('product_id', 'in', products.ids))

        history_records = self.env['product.price.history'].search(domain, order='product_id, date_changed')

        # Grouper par produit
        products_data = {}
        for record in history_records:
            product_id = record.product_id.id
            if product_id not in products_data:
                products_data[product_id] = {
                    'product': record.product_id,
                    'prices': [],
                    'currency': record.currency_id,
                    'changes': []
                }
            products_data[product_id]['prices'].append(record.new_price)
            products_data[product_id]['changes'].append(record)

        # Calculer les statistiques
        report_data = []
        for product_id, data in products_data.items():
            prices = data['prices']
            if prices:
                report_data.append({
                    'product_id': data['product'].id,
                    'product_name': data['product'].name,
                    'product_ref': data['product'].default_code or '',
                    'change_count': len(prices),
                    'highest_price': max(prices),
                    'lowest_price': min(prices),
                    'average_price': sum(prices) / len(prices),
                    'current_price': data['product'].list_price,
                    'currency': data['currency'],
                    'price_variation': max(prices) - min(prices),
                    'first_price': data['changes'][0].old_price if data['changes'] else 0,
                    'last_price': data['changes'][-1].new_price if data['changes'] else 0,
                })

        # Trier par nombre de changements (décroissant)
        report_data.sort(key=lambda x: x['change_count'], reverse=True)

        return report_data