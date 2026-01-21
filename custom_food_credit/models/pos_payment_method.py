import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosPaymentMethodInherit(models.Model):
    _inherit = 'pos.payment.method'

    is_food = fields.Boolean('Credit Alimentaire')
    is_limit = fields.Boolean('En cours / Compte client')

    @api.model
    def _load_pos_data_fields(self, config):
        """Extend POS data loading to include food credit and limit fields"""
        fields = super()._load_pos_data_fields(config)
        fields.extend(['is_food', 'is_limit'])
        return fields




