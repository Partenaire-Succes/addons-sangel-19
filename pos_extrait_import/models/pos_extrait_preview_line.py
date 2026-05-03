# -*- coding: utf-8 -*-
from odoo import models, fields


class PosExtraitPreviewLine(models.TransientModel):
    _name = 'pos.extrait.preview.line'
    _description = 'Ligne de prévisualisation import extrait POS'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        comodel_name='pos.extrait.import.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)

    # ── Données brutes ──────────────────────────────────────────────────────
    session_key  = fields.Char(string='Session',       readonly=True)
    date_order   = fields.Char(string='Date commande', readonly=True)
    order_ref    = fields.Char(string='Réf. commande', readonly=True)
    product_ref  = fields.Char(string='Code article',  readonly=True)
    product_name = fields.Char(string='Produit',       readonly=True)
    qty          = fields.Float(string='Qté',          readonly=True, digits=(12, 3))
    price_ht     = fields.Float(string='Prix HT',      readonly=True, digits=(12, 2))
    price_unit   = fields.Float(string='Prix TTC',     readonly=True, digits=(12, 2))
    margin       = fields.Float(string='Marge',        readonly=True, digits=(12, 2))

    # ── ID résolu ──────────────────────────────────────────────────────────
    resolved_product_id = fields.Integer(string='ID Produit résolu')

    # ── Statut de validation ───────────────────────────────────────────────
    line_state = fields.Selection(
        selection=[
            ('ok',    'OK'),
            ('error', 'Erreur'),
        ],
        string='Statut',
        default='ok',
        readonly=True,
    )
    message = fields.Char(string='Message', readonly=True)
