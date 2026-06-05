# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    has_bixolon_display = fields.Boolean(
        string='Afficheur Bixolon BCD-2000',
        default=False,
        help='Active l\'afficheur client Bixolon BCD-2000 via USB (Web Serial API).',
    )
