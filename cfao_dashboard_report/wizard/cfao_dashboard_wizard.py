# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date


class CfaoDashboardWizard(models.TransientModel):
    _name    = 'cfao.dashboard.wizard'
    _description = 'Assistant - Tableau de Bord Quotidien CFAO'

    analysis_date = fields.Date(
        string='Date d\'analyse',
        required=True,
        default=lambda self: date.today() - __import__('datetime').timedelta(days=1),
        help='Sélectionner la date du rapport (par défaut : hier)',
    )
    company_ids = fields.Many2many(
        'res.company',
        string='Sociétés',
        required=True,
        default=lambda self: self.env.company,
        help='Sélectionner une ou plusieurs sociétés à inclure dans le rapport',
    )
    report_format = fields.Selection([
        ('pdf',  'PDF'),
        ('xlsx', 'Excel'),
    ], string='Format', default='pdf', required=True)

    @api.constrains('analysis_date')
    def _check_date(self):
        for rec in self:
            if rec.analysis_date > date.today():
                raise UserError(_("La date d'analyse ne peut pas être dans le futur."))

    def action_print_report(self):
        self.ensure_one()
        data = {
            'analysis_date': fields.Date.to_string(self.analysis_date),
            'company_ids':   self.company_ids.ids,
        }
        return self.env.ref(
            'cfao_dashboard_report.action_report_cfao_dashboard'
        ).report_action(self, data=data)

    def action_print_xlsx(self):
        self.ensure_one()
        # Future: Excel export
        raise UserError(_("L'export Excel sera disponible dans une prochaine version."))
