# -*- coding: utf-8 -*-
import datetime
from odoo import api, fields, models


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    price_info = fields.Html(
        string="Prix à imprimer",
        compute='_compute_price_info',
    )

    @api.depends('product_ids', 'product_tmpl_ids', 'pricelist_id')
    def _compute_price_info(self):
        today = datetime.date.today()
        company = self.env.company

        # Étape 1 : récupérer les promos actives pour la société courante (une seule requête)
        active_promos = self.env['sale.promotion'].sudo().search([
            ('date_start', '<=', today),
            ('date_end', '>=', today),
            ('active', '=', True),
            '|',
            ('company_ids', '=', False),
            ('company_ids', 'in', [company.id]),
        ])

        for wizard in self:
            products = wizard.product_ids
            if not products and wizard.product_tmpl_ids:
                products = wizard.product_tmpl_ids.mapped('product_variant_ids')

            if not products:
                wizard.price_info = ''
                continue

            pricelist = wizard.pricelist_id
            rows = []

            for product in products:
                # Prix HT de base
                if pricelist:
                    price_ht = pricelist._get_product_price(
                        product, 1,
                        currency=pricelist.currency_id or product.currency_id,
                    )
                else:
                    price_ht = product.lst_price if product._name == 'product.product' else product.list_price

                # Prix TTC normal
                taxes = product.taxes_id.filtered(
                    lambda t: t.company_id == company
                )
                if taxes:
                    res = taxes.compute_all(
                        price_ht,
                        (pricelist.currency_id if pricelist else False) or product.currency_id,
                        1, product=product,
                    )
                    price_ttc = res['total_included']
                else:
                    price_ttc = price_ht

                # Étape 2 : chercher une ligne de promo pour ce produit parmi les promos actives
                promo_line = self.env['sale.promotion.line'].sudo().search([
                    ('product_id', '=', product.id),
                    ('promotion_id', 'in', active_promos.ids),
                ], limit=1)

                fmt = lambda v: '{:,.0f}'.format(v).replace(',', ' ')

                if promo_line:
                    rows.append(
                        f'<tr>'
                        f'<td style="padding:3px 10px 3px 0;max-width:200px;overflow:hidden">'
                        f'  <b>{product.display_name}</b>'
                        f'</td>'
                        f'<td style="padding:3px 10px 3px 0;text-decoration:line-through;color:#999;white-space:nowrap">'
                        f'  {fmt(price_ttc)} FCFA'
                        f'</td>'
                        f'<td style="padding:3px 0;color:#cc0000;font-weight:bold;white-space:nowrap">'
                        f'  {fmt(promo_line.promo_ttc)} FCFA'
                        f'  <span style="font-size:0.85em;font-weight:normal">'
                        f'    &nbsp;(−{promo_line.discount:.2f}% — {promo_line.promotion_id.name})'
                        f'  </span>'
                        f'</td>'
                        f'</tr>'
                    )
                else:
                    rows.append(
                        f'<tr>'
                        f'<td style="padding:3px 10px 3px 0;max-width:200px;overflow:hidden">'
                        f'  <b>{product.display_name}</b>'
                        f'</td>'
                        f'<td colspan="2" style="padding:3px 0;white-space:nowrap">'
                        f'  {fmt(price_ttc)} FCFA'
                        f'</td>'
                        f'</tr>'
                    )

            wizard.price_info = (
                '<table style="width:100%;border-collapse:collapse">'
                + ''.join(rows)
                + '</table>'
            )
