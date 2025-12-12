from odoo import models, fields, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    code_acces = fields.Char(string="Code d'accès pour rupture de stock")