from odoo import fields, models, api, _


class BudgetAnalyticInherit(models.Model):
    _inherit = 'budget.analytic'

    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Compte Analytique',
    )
    daily_budget_id = fields.Many2one(
        'daily.budget.analytic',
        string='Budget_journalier',
    )

    def action_budget_done(self):
        res = super(BudgetAnalyticInherit, self).action_budget_done()
        for budget in self:
            if budget.daily_budget_id:
                budget.action_close()
        return res
    
    
    def unlink(self):
        for budget in self:
            if budget.daily_budget_id:
                budget.action_draft()
        return super().unlink()