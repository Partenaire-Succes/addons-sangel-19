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

    def _select(self):
        """Extend SELECT to include nature fields"""
        return super()._select() + """,
                pt.nature_id AS nature_id,
                COALESCE(pt.nature_quantity, 0) AS nature_quantity,
                CAST(l.qty * COALESCE(pt.nature_quantity, 0) AS INTEGER) AS total_nature_qty
        """
