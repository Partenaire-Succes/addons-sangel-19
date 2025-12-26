# -*- coding: utf-8 -*-
from odoo import api, models


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, config):
        """Add loyalty.family to the list of models loaded in POS"""
        result = super()._load_pos_data_models(config)
        result.append('loyalty.family')
        return result
