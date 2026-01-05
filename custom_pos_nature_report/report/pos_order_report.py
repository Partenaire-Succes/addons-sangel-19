# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ReportPosOrderNature(models.Model):
    """
    Extension of report.pos.order to add nature tracking fields and custom price calculations.
    - Nature tracking: tracks actual quantities sold by nature (e.g., macarons from coffrets)
    - Custom HT/TTC: calculates based on product list_price and taxes, not transaction prices
    """
    _inherit = 'report.pos.order'

    nature_id = fields.Many2one(
        'product.nature',
        string='Nature',
        readonly=True,
        help="Nature du produit (ex: Macaron, Eugenie)"
    )
    nature_quantity = fields.Integer(
        string='Qté nature/unité',
        readonly=True,
        aggregator='avg',  # Use average so pivot shows actual value (4) not sum (24)
        help="Quantité de nature par unité de produit"
    )
    total_nature_qty = fields.Integer(
        string='Qté nature totale',
        readonly=True,
        help="Quantité totale de nature vendue (qty × nature_quantity)"
    )
    nature_unit_price = fields.Float(
        string='Valeur unitaire',
        readonly=True,
        aggregator='avg',  # Use average to show unit price, not sum
        help="Prix unitaire par nature (défini sur la nature)"
    )
    valeur_monetaire = fields.Float(
        string='Valeur monétaire',
        readonly=True,
        help="Valeur monétaire = Qté nature totale × Prix unitaire"
    )
    price_total_ht = fields.Float(
        string='Prix total HT',
        readonly=True,
        help="Prix total HT = Prix de base (list_price) × Quantité de produits vendus"
    )
    price_total_ttc = fields.Float(
        string='Prix total TTC',
        readonly=True,
        help="Prix total TTC = Prix de base × (1 + taux de taxe) × Quantité de produits vendus"
    )

    def _select(self):
        """Extend SELECT to include nature fields, valeur monetaire, and custom HT/TTC calculations
        
        Prix total HT = list_price × qty
        Prix total TTC = ((list_price × tax_rate) + list_price) × qty
                       = list_price × (1 + tax_rate) × qty
                       → arrondi au millier supérieur avec CEIL()
        """
        return super()._select() + """,
                pt.nature_id AS nature_id,
                COALESCE(pt.nature_quantity, 0) AS nature_quantity,
                CAST(l.qty * COALESCE(pt.nature_quantity, 0) AS INTEGER) AS total_nature_qty,
                COALESCE(pn.unit_price, 0) AS nature_unit_price,
                (l.qty * COALESCE(pt.nature_quantity, 0)) * COALESCE(pn.unit_price, 0) AS valeur_monetaire,
                pt.list_price * l.qty AS price_total_ht,
                CEIL(pt.list_price * (1 + COALESCE(tax_agg.total_tax_percent, 0) / 100) * l.qty / 1000) * 1000 AS price_total_ttc
        """

    def _from(self):
        """Extend FROM to join product_nature table and get first sale tax"""
        return super()._from() + """
                LEFT JOIN product_nature pn ON (pt.nature_id = pn.id)
                LEFT JOIN LATERAL (
                    SELECT COALESCE(tax.amount, 0) AS total_tax_percent
                    FROM product_taxes_rel ptr
                    JOIN account_tax tax ON tax.id = ptr.tax_id
                        AND tax.type_tax_use = 'sale'
                        AND tax.amount_type = 'percent'
                    WHERE ptr.prod_id = pt.id
                    ORDER BY tax.id
                    LIMIT 1
                ) tax_agg ON true
        """
