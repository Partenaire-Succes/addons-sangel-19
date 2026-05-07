# -*- coding: utf-8 -*-
from odoo import models, fields


class StockAvcoCorrectionLine(models.TransientModel):
    _name = 'stock.avco.correction.line'
    _description = 'Ligne Correction AVCO'

    wizard_id       = fields.Many2one('stock.avco.correction.wizard', ondelete='cascade')
    product_id      = fields.Many2one('product.product', string='Article',    readonly=True)
    default_code    = fields.Char(string='Code Article',    readonly=True)
    product_name    = fields.Char(string='Nom Article',     readonly=True)
    correct_price   = fields.Float(string='Prix correct',   digits=(16, 4), readonly=True)
    qty_zero_svl    = fields.Float(string='Qté reçue à 0',  digits=(16, 3), readonly=True)
    value_to_inject = fields.Float(string='Valeur à injecter', digits=(16, 2), readonly=True)
    current_avco    = fields.Float(string='AVCO actuel',    digits=(16, 4), readonly=True)
    current_qty     = fields.Float(string='Stock actuel',   digits=(16, 3), readonly=True)
    new_avco        = fields.Float(string='AVCO corrigé',   digits=(16, 4), readonly=True)
    line_state      = fields.Selection([
        ('ok',      'OK'),
        ('warning', 'Avertissement'),
        ('error',   'Erreur'),
    ], string='Statut', readonly=True)
    message         = fields.Char(string='Message', readonly=True)
