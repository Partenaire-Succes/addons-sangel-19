from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'
    _rec_name = 'name'

    food_id = fields.Many2one(
        "food.credit",
        string="Crédit Alimentaire",
        copy=False,
    )

class AccountMoveLineInherit(models.Model):
    _inherit = 'account.move.line'

    invoice_text = fields.Text('Factures')


