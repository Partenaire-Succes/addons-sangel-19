import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    is_loyalty = fields.Boolean('A une carte de fidélité', default=True)
    
    @api.model
    def _load_pos_data_fields(self, config):
        """Ajouter is_loyalty aux données chargées dans le POS pour le mode hors-ligne"""
        fields = super()._load_pos_data_fields(config)
        fields.append('is_loyalty')
        return fields
    
    @api.onchange('loyalty_card_ids')
    def get_loyalty_card(self):
        """Met à jour la carte de fidélité en fonction du client sélectionnée"""
        if self.loyalty_card_ids:
            self.is_loyalty = True
        else:
            self.is_loyalty = False