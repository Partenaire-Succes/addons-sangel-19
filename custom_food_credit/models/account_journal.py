from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class AccountJournalInherit(models.Model):
    _inherit = 'account.journal'

    is_food = fields.Boolean('Credit Alimentaire', default=False)
    is_limit = fields.Boolean(string="Limite de crédit", default=False)