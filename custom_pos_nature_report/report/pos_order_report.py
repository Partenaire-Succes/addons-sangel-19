# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class ReportPosOrderNature(models.Model):
    """
    Extension of report.pos.order to add nature tracking fields.
    This allows tracking actual quantities sold by nature
    (e.g., how many macarons were sold in total from different coffrets)
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
        string='Prix unitaire',
        readonly=True,
        aggregator='avg',  # Use average to show unit price, not sum
        help="Prix unitaire par nature (défini sur la nature)"
    )
    valeur_monetaire = fields.Float(
        string='Valeur monétaire',
        readonly=True,
        help="Valeur monétaire = Qté nature totale × Prix unitaire"
    )
    price_total_list = fields.Float(
        string='Prix total TTC',
        readonly=True,
        help="Total basé sur le prix de base (prix catalogue × quantité)"
    )

    def _select(self):
        """Extend SELECT to include nature fields and valeur monetaire calculations"""
        return super()._select() + """,
                pt.nature_id AS nature_id,
                COALESCE(pt.nature_quantity, 0) AS nature_quantity,
                CAST(l.qty * COALESCE(pt.nature_quantity, 0) AS INTEGER) AS total_nature_qty,
                COALESCE(pn.unit_price, 0) AS nature_unit_price,
                (l.qty * COALESCE(pt.nature_quantity, 0)) * COALESCE(pn.unit_price, 0) AS valeur_monetaire,
                l.qty * pt.list_price AS price_total_list
        """

    def _from(self):
        """Extend FROM to join product_nature table for unit_price"""
        return super()._from() + """
                LEFT JOIN product_nature pn ON (pt.nature_id = pn.id)
        """
