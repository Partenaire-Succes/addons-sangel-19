from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class AccountJournalInherit(models.Model):
    _inherit = 'account.journal'

    is_payment_sage = fields.Boolean('Inclus ENCAI', default=False)
    