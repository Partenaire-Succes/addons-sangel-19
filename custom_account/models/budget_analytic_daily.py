import logging
import re
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class BudgetAnalyticDaily(models.Model):
    _name = 'daily.budget.analytic'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Daily Budget Analytic'
    _rec_name = 'name'
    _order = 'create_date desc'
    
    name = fields.Char(
        string='Nom du budget',
        required=True,
    )
    date_from = fields.Datetime(
        string='Date de début',
        required=True,
        default=fields.Date.context_today
    )
    date_to = fields.Datetime(
        string='Date de fin',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company
    )
    budget_type = fields.Selection([
            ('revenue', 'Revenu'), 
            ('expense', 'Note de frais'), 
            ('both', 'Les deux')
        ], string='Type de budget', 
            default='revenue', 
            required=True
    )

    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Compte Analytique',
    )

    plan_analytic_id = fields.Many2one(
        'account.analytic.plan',
        string='Plan Analytique',
    )

    budget_id = fields.Many2one(
        'budget.analytic',
        string='Budget Analytique'
    )
    budget_amount = fields.Monetary(
        string="Budget Mensuel",
        compute="_compute_budget_amount",
        store=True
    )
    currency_id = fields.Many2one(
        string="Currency",
        related='company_id.currency_id',
        readonly=True)
    note = fields.Text(
        string='Description'
    )
    state = fields.Selection(
        [
            ('draft', 'Brouillon'), 
            ('pending', 'En attente'), 
            ('in_progress', 'En cours'), 
            ('done', 'Terminé')
        ], string='État', 
        default='draft', 
        required=True
    )
    line_ids = fields.One2many(
        'daily.budget.analytic.line', 
        'daily_budget_id',
        string='Les lignes de budget journaliere', 
        copy=True
    )

    @api.depends('line_ids.budget_amount')
    def _compute_budget_amount(self):
        for record in self:
            record.budget_amount = sum(record.line_ids.mapped('budget_amount'))


    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_("La date de fin doit être postérieure à la date de début."))

    def action_generate(self):
        """Passe le budget en cours et génère les lignes journalières"""
        self.ensure_one()
        self._generate_daily_lines()
        self.write({'state': 'pending'})


    def action_done(self):
        """Passe le budget en cours et génère les lignes journalières"""
        self.ensure_one()
        self._generate_budget()

        if not self.line_ids:
            raise ValidationError(_("Aucune ligne générée. Vérifiez les dates du budget."))

        for line in self.line_ids:
            if line.budget_amount <= 0:
                raise ValidationError(_("Le budget des lignes générées doit être strictement supérieur à zéro."))

        self.write({'state': 'in_progress'})

    def action_close(self):
        if self.budget_id:
            self.budget_id.with_context(skip_daily_budget_sync=True).action_budget_done()
        self.write({'state': 'done'})

    def action_draft(self):
        if self.line_ids:
            self.line_ids.unlink()
        self.write({'state': 'draft'})

    def _generate_daily_lines(self):
        """Génère une ligne pour chaque jour de la période"""
        self.ensure_one()
        self.line_ids.unlink()
        
        date_from = self.date_from.date() if isinstance(self.date_from, datetime) else self.date_from
        date_to = self.date_to.date() if isinstance(self.date_to, datetime) else self.date_to
        
        delta = date_to - date_from
        num_days = delta.days + 1
        
        # Calculer le budget journalier
        daily_amount = self.budget_amount / num_days if num_days > 0 else 0
        
        # Créer une ligne pour chaque jour
        lines_to_create = []
        current_date = date_from
        
        while current_date <= date_to:
            line_name = f"Budget du {current_date.strftime('%d/%m/%Y')}"
            
            # Forcer début et fin de journée
            date_from_dt = datetime.combine(current_date, time(0, 0, 0))
            date_to_dt   = datetime.combine(current_date, time(23, 59, 59))
            
            line_vals = {
                'name': line_name,
                'date_from': date_from_dt,
                'date_to': date_to_dt,
                'company_id': self.company_id.id,
                'account_analytic_id': self.account_analytic_id.id,
                'plan_analytic_id': self.plan_analytic_id.id,
                'daily_budget_id': self.id,
            }
            lines_to_create.append(line_vals)
            current_date += timedelta(days=1)
        
        # Créer toutes les lignes en une seule fois
        self.env['daily.budget.analytic.line'].create(lines_to_create)
        
        return True
    
    def _generate_budget(self):
        """Génère une ligne pour chaque jour de la période"""
        
        # Créer une ligne pour chaque jour
        for rec in self:

            date_from = self.date_from.date() if isinstance(self.date_from, datetime) else self.date_from
            date_to = self.date_to.date() if isinstance(self.date_to, datetime) else self.date_to
            budget_create = self.env['budget.analytic']

            line_vals = {
                'daily_budget_id': rec.id,
                'name': rec.name,
                'budget_type': rec.budget_type,
                'account_analytic_id': rec.account_analytic_id.id,
                'user_id': self.env.user.id,
                'date_from': date_from,
                'date_to': date_to,
                'company_id': rec.company_id.id,
            }
        
            # Créer toutes les lignes en une seule fois
            budget = budget_create.create(line_vals)
            self.budget_id = budget.id
        
        return True

    @api.onchange('date_from', 'date_to')
    def _onchange_dates_budget(self):
        """Recalcule les lignes si les dates ou le budget changent"""
        if self.state == 'draft' and self.date_from and self.date_to and self.line_ids:
            return {
                'warning': {
                    'title': _("Attention"),
                    'message': _("Les lignes journalières seront régénérées lors de la validation du budget.")
                }
            }



class BudgetAnalyticDailyLine(models.Model):
    _name = 'daily.budget.analytic.line'
    _rec_name = 'name'
    
    name = fields.Char(
        string='Nom du budget',
        required=True,
    )
    date_from = fields.Datetime(
        string='Date de début',
        required=True,
        default=fields.Date.context_today
    )
    date_to = fields.Datetime(
        string='Date de fin',
        required=True,
        default=fields.Date.context_today
    )
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company
    )
    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Compte Analytique',
        required=True
    )
    plan_analytic_id = fields.Many2one(
        'account.analytic.plan',
        string='Plan Analytique',
    )
    budget_amount = fields.Monetary(
        string="Budget Mensuel"
    )
    currency_id = fields.Many2one(
        string="Currency",
        related='company_id.currency_id',
        readonly=True
    )
    daily_budget_id = fields.Many2one(
        'daily.budget.analytic',
        string="Budget",
        ondelete='cascade'
    )
    state = fields.Selection(
        related='daily_budget_id.state',
    )
    actual_amount = fields.Monetary(
        string="Montant Réel",
        compute='compute_actual_amount',
        store=True
    )
    variance = fields.Monetary(
        string="Écart",
        compute='_compute_variance',
        store=True
    )
    variance_percent = fields.Float(
        string="Réalisé (%)",
        compute='_compute_variance',
        store=True
    )

    @api.depends('account_analytic_id', 'date_from', 'date_to')
    def compute_actual_amount(self):
        for line in self:
            if not line.account_analytic_id or not line.date_from or not line.date_to:
                line.actual_amount = 0.0
                continue

            # account.move.line.date is a Date field; ensure we compare with dates,
            # not datetimes.
            date_from = line.date_from.date() if isinstance(line.date_from, datetime) else line.date_from
            date_to = line.date_to.date() if isinstance(line.date_to, datetime) else line.date_to
            
            move_lines = self.env['account.move.line'].sudo().search([
                ('distribution_analytic_account_ids', 'in', [line.account_analytic_id.id]),
                ('parent_state', '=', 'posted'),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ])
            
            line.actual_amount = sum(move_lines.mapped('credit'))


    @api.depends('budget_amount', 'actual_amount')
    def _compute_variance(self):
        """Calcule l'écart entre le budget et le réel"""
        for line in self:
            line.variance = line.budget_amount - line.actual_amount
            
            # Calculer le pourcentage d'écart
            if line.budget_amount != 0:
                line.variance_percent = (line.actual_amount / line.budget_amount)
            else:
                line.variance_percent = 0.0
