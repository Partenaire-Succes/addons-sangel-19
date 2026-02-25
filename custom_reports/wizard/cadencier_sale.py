# -*- coding: utf-8 -*-
from odoo import fields, models, api
from datetime import date
from collections import defaultdict


class CadencierWizard(models.TransientModel):
    _name = 'cadencier.ventes.wizard'
    _description = 'Wizard Cadencier Stat Ventes Articles'

    year = fields.Selection(
        selection='_get_years',
        string="Année",
        required=True,
        default=lambda self: str(date.today().year),
    )
    company_id = fields.Many2one(
        'res.company',
        string="Société",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )
    famille_ids = fields.Many2many(
        'product.category',
        string="Familles (optionnel)",
        help="Laisser vide pour toutes les familles",
    )

    @api.model
    def _get_years(self):
        current_year = date.today().year
        return [(str(y), str(y)) for y in range(current_year - 5, current_year + 2)]

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('custom_reports.action_report_cadencier').report_action(self)

    def _get_report_data(self, year, company_id, famille_ids=None):
        company = self.env['res.company'].browse(company_id)
        date_from = date(int(year), 1, 1)
        date_to = date(int(year), 12, 31)

        sale_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.company_id', '=', company_id),
            ('order_id.date_order', '>=', str(date_from)),
            ('order_id.date_order', '<=', str(date_to)),
        ]
        sale_lines = self.env['sale.order.line'].search(sale_domain)

        pos_domain = [
            ('order_id.state', 'in', ['done', 'paid', 'invoiced']),
            ('order_id.company_id', '=', company_id),
            ('order_id.date_order', '>=', str(date_from)),
            ('order_id.date_order', '<=', str(date_to)),
        ]
        pos_lines = self.env['pos.order.line'].search(pos_domain)

        product_data = defaultdict(lambda: defaultdict(float))

        for line in sale_lines:
            month_idx = line.order_id.date_order.month - 1
            product_data[line.product_id.id][month_idx] += line.product_uom_qty

        for line in pos_lines:
            month_idx = line.order_id.date_order.month - 1
            product_data[line.product_id.id][month_idx] += line.qty

        if not product_data:
            return []

        product_ids = list(product_data.keys())
        products = self.env['product.product'].browse(product_ids)

        if famille_ids:
            products = products.filtered(
                lambda p: p.categ_id.id in famille_ids
            )

        result = []
        for product in products.sorted(key=lambda p: ((p.categ_id.name or '').lower(), (p.default_code or '').lower())):
            monthly_qtys = product_data[product.id]
            ventes = [round(monthly_qtys.get(i, 0), 2) for i in range(12)]
            total = sum(ventes)
            stock = product.with_company(company).qty_available
            pmp = product.avg_cost if product.avg_cost else product.standard_price

            # ✅ CA réel depuis les lignes de vente (après remises)
            total_ca = 0.0
            for line in sale_lines:
                if line.product_id.id == product.id:
                    total_ca += line.price_subtotal  # HT après remise

            for line in pos_lines:
                if line.product_id.id == product.id:
                    total_ca += line.price_subtotal  # HT après remise POS

            # ✅ Coût total cumulé sur l'année
            total_cost = total * pmp

            # ✅ Taux de marge cumulé = (CA - Coût) / CA * 100
            taux_marge = round((total_ca - total_cost) / total_ca * 100, 2) if total_ca > 0 else 0.0

            result.append({
                'code': product.default_code or '',
                'designation': product.name,
                'sta': product.prod_status_x3_id.name if product.prod_status_x3_id else '',
                'maxi': product.max_qty_orderpoint,
                'cmd': product.pending_reception_qty,
                'marg': taux_marge,
                'famille': product.categ_id.name,
                'code_famille': product.categ_id.code,
                'st_disp': round(stock, 2),
                'pvtc': product.list_price,
                'ventes': ventes,
                'total': total,
            })

        return result


class ReportCadencierVentes(models.AbstractModel):
    _name = 'report.custom_reports.report_cadencier_template'
    _description = 'Rapport Cadencier Ventes'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['cadencier.ventes.wizard'].browse(docids)
        lines = wizard._get_report_data(
            wizard.year,
            wizard.company_id.id,
            wizard.famille_ids.ids,
        )
        return {
            'doc': wizard,
            'company': wizard.company_id,
            'year': wizard.year,
            'lines': lines,
        }