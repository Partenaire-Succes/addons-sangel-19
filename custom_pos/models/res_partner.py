# -*- coding: utf-8 -*-
from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if 'is_airsi_eligible' not in fields:
            fields.append('is_airsi_eligible')
        return fields
