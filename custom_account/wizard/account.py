from odoo import models, fields, api
from odoo.exceptions import UserError


class BudgetAnalyticWizard(models.TransientModel):
    _name = 'budget.analytic.wizard'
    _description = 'Budget journalier'

    