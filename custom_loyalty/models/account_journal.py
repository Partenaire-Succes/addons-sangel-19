from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class AccountJournalInherit(models.Model):
    _inherit = 'account.journal'

    is_loyalty = fields.Boolean('Carte de fidélité', default=False)