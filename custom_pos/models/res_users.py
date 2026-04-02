# -*- coding: utf-8 -*-
from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        if read_records:
            # _is_caissiere / _is_dsi_it : préfixe _ requis par Odoo 18/19 pour créer le getter JS automatiquement
            read_records[0]['_is_caissiere'] = self.env.user.has_group('custom_pos.group_caissiere')
            # read_records[0]['_is_dsi_it'] = self.env.user.has_group('custom_pos.group_dsi_it')
        return read_records
