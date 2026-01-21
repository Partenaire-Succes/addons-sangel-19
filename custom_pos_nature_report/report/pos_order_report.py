# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ReportPosOrderNature(models.Model):
    """
    Extension of report.pos.order to add nature tracking fields and fix price calculations.
    - Nature tracking: tracks actual quantities sold by nature (e.g., macarons from coffrets)
    - Price fix: native price_total doesn't respect refund signs (SIGN(qty) fix)
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

    def _select(self):
        """Extend SELECT to include nature fields and fix price_total for refunds.
        
        IMPORTANT FIX: Native price_total uses price_subtotal_incl which is always positive,
        even for refund lines. This breaks pivot aggregation. We override it by multiplying
        by SIGN(l.qty) so refund lines contribute negative amounts to the total.
        
        Also adds custom HT calculation based on list_price.
        """
        # Get the base SELECT but we need to override price_total
        base_select = super()._select()
        
        # Replace the native price_total calculation with sign-aware version
        # Native: ROUND((l.price_subtotal_incl) / COALESCE(NULLIF(s.currency_rate, 0), 1.0), cu.decimal_places) AS price_total
        # Fixed:  Multiply by SIGN(l.qty) to respect refunds
        base_select = base_select.replace(
            'ROUND((l.price_subtotal_incl) / COALESCE(NULLIF(s.currency_rate, 0), 1.0), cu.decimal_places) AS price_total',
            'ROUND((l.price_subtotal_incl * SIGN(COALESCE(l.qty, 1))) / COALESCE(NULLIF(s.currency_rate, 0), 1.0), cu.decimal_places) AS price_total'
        )
        
        return base_select + """,
                pt.nature_id AS nature_id,
                COALESCE(pt.nature_quantity, 0) AS nature_quantity,
                CAST(l.qty * COALESCE(pt.nature_quantity, 0) AS INTEGER) AS total_nature_qty,
                COALESCE(pn.unit_price, 0) AS nature_unit_price,
                (l.qty * COALESCE(pt.nature_quantity, 0)) * COALESCE(pn.unit_price, 0) AS valeur_monetaire,
                pt.list_price * l.qty AS price_total_ht
        """

    def _from(self):
        """Extend FROM to join product_nature table"""
        return super()._from() + """
                LEFT JOIN product_nature pn ON (pt.nature_id = pn.id)
        """
