# -*- coding: utf-8 -*-
from odoo import models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if 'is_airsi' not in fields:
            fields.append('is_airsi')
        return fields
