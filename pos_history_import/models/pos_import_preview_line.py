# -*- coding: utf-8 -*-
from odoo import models, fields


class PosImportPreviewLine(models.TransientModel):
    _name = 'pos.import.preview.line'
    _description = 'Ligne de prévisualisation import POS'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        comodel_name='pos.history.import.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)

    # ── Données brutes de la ligne ──────────────────────────────────────────
    date_order      = fields.Char(string='Date commande',   readonly=True)
    order_ref       = fields.Char(string='Réf. commande',   readonly=True)
    customer_info   = fields.Char(string='Client',          readonly=True)
    product_ref     = fields.Char(string='Réf. produit',    readonly=True)
    product_name    = fields.Char(string='Produit',         readonly=True)
    qty             = fields.Float(string='Qté',            readonly=True, digits=(12, 2))
    price_unit      = fields.Float(string='Prix unit.',     readonly=True, digits=(12, 2))
    discount        = fields.Float(string='Remise %',       readonly=True, digits=(5, 2))
    payment_method  = fields.Char(string='Mode paiement',  readonly=True)
    amount_paid     = fields.Float(string='Montant payé',   readonly=True, digits=(12, 2))
    note            = fields.Char(string='Note',            readonly=True)
    session_key     = fields.Char(string='Session',         readonly=True)

    # ── IDs résolus (utilisés lors du vrai import) ─────────────────────────
    resolved_product_id        = fields.Integer(string='ID Produit résolu')
    resolved_partner_id        = fields.Integer(string='ID Client résolu')
    resolved_payment_method_id = fields.Integer(string='ID Mode paiement résolu')

    # ── Type de ligne ─────────────────────────────────────────────────────
    line_type = fields.Selection(
        selection=[('product', 'Produit'), ('payment', 'Paiement')],
        string='Type',
        default='product',
        readonly=True,
    )

    # ── Statut de validation ───────────────────────────────────────────────
    line_state = fields.Selection(
        selection=[
            ('ok',      'OK'),
            ('warning', 'Avertissement'),
            ('error',   'Erreur'),
        ],
        string='Statut',
        default='ok',
        readonly=True,
    )
    message = fields.Char(string='Message', readonly=True)
