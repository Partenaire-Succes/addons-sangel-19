from odoo import models, fields, api


class AccountTaxInherit(models.Model):
    _inherit = 'account.tax'

    is_airsi = fields.Boolean(
        string='Est une taxe AIRSI',
        default=False,
        help='''
            Cocher si cette taxe est une taxe AIRSI 
            (appliquée uniquement pour les clients à 
            limite avec paiement à crédit)
        '''
    )