# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools import float_round


class StockValoriseReport(models.TransientModel):
    _name = 'stock.valorise.report'
    _description = 'Rapport de Stock Valorisé'

    date_report = fields.Date(
        string='Date de valorisation',
        required=True,
        default=fields.Date.context_today
    )

    location_id = fields.Many2one(
        'stock.location',
        string='Emplacement',
        required=True,
        domain=[('usage', '=', 'internal')]
    )

    category_ids = fields.Many2many(
        'product.category',
        string='Catégories'
    )

    product_ids = fields.Many2many(
        'product.product',
        string='Produits',
        compute='_compute_product_ids',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Société',
        default=lambda self: self.env.company,
    )


    @api.depends('company_id', 'category_ids')
    def _compute_product_ids(self):
        """Détermine les produits concernés par la société et les catégories choisies."""
        for record in self:
            domain = [
                '|',
                ('company_id', '=', record.company_id.id),
                ('company_id', '=', False)
            ]
            if record.category_ids:
                domain.append(('categ_id', 'in', record.category_ids.ids))

            record.product_ids = self.env['product.product'].search(domain)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        if 'location_id' in fields_list and not res.get('location_id'):
            location = self.env['stock.location'].search([
                ('usage', '=', 'internal'),
                '|',
                ('name', 'ilike', 'Stock'),
                ('complete_name', 'ilike', '/Stock')
            ], limit=1)

            if not location:
                warehouse = self.env['stock.warehouse'].search([
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
                if warehouse:
                    location = warehouse.lot_stock_id

            if not location:
                location = self.env['stock.location'].search([
                    ('usage', '=', 'internal')
                ], limit=1)

            if location:
                res['location_id'] = location.id

        return res

    # -------------------------------------------------------------------------
    # LOGIQUE DU RAPPORT
    # -------------------------------------------------------------------------
    def _get_stock_by_category(self):
        """Retourne les données de valorisation à partir de product_ids."""
        self.ensure_one()
        categories = {}

        total_articles = 0
        total_qty = 0.0
        total_valorisation = 0.0

        for product in self.product_ids:
            categ = product.categ_id
            categ_id = categ.id

            # 🧠 Code article géré proprement
            code_article = product.code_article or product.product_tmpl_id.code_article or ''

            # Stock réel dans l'emplacement
            qty = product.with_context(location=self.location_id.id).qty_available
            if not qty or qty <= 0:
                continue

            pamp = product.standard_price or 0.0
            valorisation = float_round(qty * pamp, 2)

            if categ_id not in categories:
                categories[categ_id] = {
                    'category': categ.name,
                    'category_code': categ.complete_name or categ.name,
                    'products': [],
                    'total': 0.0,
                }

            categories[categ_id]['products'].append({
                'code_article': code_article,
                'default_code': product.default_code or '',
                'name': product.name,
                'category_code': categ.name,
                'qty': float_round(qty, 2),
                'pamp': float_round(pamp, 2),
                'valorisation': valorisation,
            })

            categories[categ_id]['total'] += valorisation
            total_articles += 1
            total_qty += qty
            total_valorisation += valorisation

        pamp_moyen = float_round(total_valorisation / total_qty, 2) if total_qty else 0.0

        return {
            'categories': sorted(categories.values(), key=lambda c: c['category']),
            'total_articles': total_articles,
            'total_qty': float_round(total_qty, 2),
            'pamp_moyen': pamp_moyen,
            'total_valorisation': float_round(total_valorisation, 2),
        }

    # -------------------------------------------------------------------------
    # ACTION DE RAPPORT
    # -------------------------------------------------------------------------


    def action_print_report(self):
        """Générer le rapport PDF et fermer le wizard"""
        self.ensure_one()

        # 1️⃣ Lancer le rapport PDF
        report_action = self.env.ref('custom_reports.action_report_stock_valorise').report_action(self)

        # 2️⃣ Ajouter l'action de fermeture
        report_action['close_on_report_download'] = True

        return report_action





