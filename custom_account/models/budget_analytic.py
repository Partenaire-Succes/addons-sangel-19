from odoo import _, api, fields, models


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

        # Keep the linked daily budget in sync, without calling back methods
        # that would re-trigger budget closure and create recursion.
        if self.env.context.get('skip_daily_budget_sync'):
            return res

        for budget in self:
            if budget.daily_budget_id and budget.daily_budget_id.state != 'done':
                budget.daily_budget_id.write({'state': 'done'})
        return res
    
    
    def unlink(self):
        for budget in self:
            if budget.daily_budget_id:
                budget.daily_budget_id.action_draft()
        return super().unlink()