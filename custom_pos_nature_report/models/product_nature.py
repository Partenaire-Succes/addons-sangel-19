# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductNature(models.Model):
    """
    Model to define product natures like Macaron, Eugenie, etc.
    Used to track actual quantities sold (e.g., COFFRET-4 = 4 macarons)
    """
    _name = 'product.nature'
    _description = 'Nature du produit'
    _order = 'name'

    name = fields.Char(
        string='Nom',
        required=True,
        translate=True,
        help="Nom de la nature (ex: Macaron, Eugenie)"
    )
    unit_price = fields.Float(
        string='Valeur unitaire',
        default=0.0,
        digits='Product Price',
        help="Prix unitaire par nature (utilisé pour calculer la valeur monétaire)"
    )
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Le nom de la nature doit être unique!')
    ]


class ProductTemplateNature(models.Model):
    """
    Extension of product.template to add nature tracking fields
    """
    _inherit = 'product.template'

    nature_id = fields.Many2one(
        'product.nature',
        string='Nature',
        help="Nature du produit pour le suivi (ex: Macaron, Eugenie)"
    )
    nature_quantity = fields.Integer(
        string='Quantité nature',
        default=0,
        help="Quantité de la nature par unité vendue (ex: COFFRET-4 = 4 macarons)"
    )
