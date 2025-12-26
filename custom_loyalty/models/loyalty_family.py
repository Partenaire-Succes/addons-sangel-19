# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LoyaltyFamily(models.Model):
    _name = 'loyalty.family'
    _inherit = ['pos.load.mixin']
    _description = 'Famille de fidélité'
    _order = 'price_threshold, points_earned'

    name = fields.Char(
        string='Nom',
        compute='_compute_name',
        store=True,
        readonly=False,
    )
    
    points_earned = fields.Integer(
        string='Points gagnés',
        required=True,
        default=1,
        help="Nombre de points de fidélité gagnés"
    )
    
    price_threshold = fields.Float(
        string='Montant à dépenser (FCFA)',
        required=True,
        default=200.0,
        help="Montant minimum à dépenser pour gagner les points"
    )
    
    active = fields.Boolean(
        string='Actif',
        default=True,
    )
    
    product_category_ids = fields.One2many(
        'product.category',
        'family_loyalty_id',
        string='Catégories de produits',
    )
    
    @api.depends('points_earned', 'price_threshold')
    def _compute_name(self):
        for record in self:
            if record.points_earned and record.price_threshold:
                point_label = 'point' if record.points_earned == 1 else 'points'
                record.name = f"{record.points_earned} {point_label} / {int(record.price_threshold)} F"
            else:
                record.name = _('Nouvelle famille fidélité')
    
    @api.constrains('points_earned', 'price_threshold')
    def _check_values(self):
        for record in self:
            if record.points_earned <= 0:
                raise ValidationError(_("Le nombre de points doit être supérieur à zéro."))
            if record.price_threshold <= 0:
                raise ValidationError(_("Le montant à dépenser doit être supérieur à zéro."))
    
    def name_get(self):
        """Override to ensure consistent display name"""
        result = []
        for record in self:
            point_label = 'point' if record.points_earned == 1 else 'points'
            name = f"{record.points_earned} {point_label} / {int(record.price_threshold)} F"
            result.append((record.id, name))
        return result
    
    # === POS Data Loading ===
    
    @api.model
    def _load_pos_data_domain(self, data, config):
        """Domain for loading loyalty families in POS"""
        return [('active', '=', True)]
    
    @api.model
    def _load_pos_data_fields(self, config):
        """Fields to load for POS"""
        return ['id', 'name', 'points_earned', 'price_threshold', 'active']
