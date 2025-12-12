from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class PosPaymentMethodInherit(models.Model):
    _inherit = 'pos.payment.method'

    is_loyalty = fields.Boolean('Carte de fidélité')




