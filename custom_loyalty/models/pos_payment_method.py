from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class PosPaymentMethodInherit(models.Model):
    _inherit = 'pos.payment.method'

    is_loyalty = fields.Boolean('Carte de fidélité')

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if 'is_loyalty' not in fields:
            fields.append('is_loyalty')
        return fields