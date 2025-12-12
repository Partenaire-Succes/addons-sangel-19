from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    is_loyalty = fields.Boolean('A une carte de fidélité', default=True)
    
    @api.onchange('loyalty_card_ids')
    def get_loyalty_card(self):
        """Met à jour la carte de fidélité en fonction du client sélectionnée"""
        if self.loyalty_card_ids:
            self.is_loyalty = True
        else:
            self.is_loyalty = False