from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class PosPaymentMethodInherit(models.Model):
    _inherit = 'pos.payment.method'

    is_food = fields.Boolean('Credit Alimentaire')
    is_limit = fields.Boolean('En cours / Compte client')




