from odoo import models, fields, api, _
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class ReliquatReportWizard(models.TransientModel):
    _name = 'reliquat.report.wizard'
    _description = 'Assistant de création de rapport de non livrés'


    period_type = fields.Selection([
        ('daily', 'Quotidien'),
        ('weekly', 'Hebdomadaire'),
        ('biweekly', 'Quinzaine'),
        ('monthly', 'Mensuel'),
        ('quarterly', 'Trimestriel'),
        ('semiannual', 'Semestriel'),
        ('yearly', 'Annuel'),
        ('custom', 'Personnalisé')
    ], string='Type de période', required=True, default='monthly')

    date_from = fields.Date(string='Date de début')
    date_to = fields.Date(string='Date de fin')


    def action_generate_report(self):
        """Crée le rapport avec un nom formaté jj/mm/aaaa"""
        if not self.date_from:
            raise ValueError(_("Veuillez définir la date de début."))

        date_from_str = self.date_from.strftime('%d/%m/%Y')
        date_to_str = self.date_to.strftime('%d/%m/%Y') if self.date_to else None

        if self.date_to and self.date_from != self.date_to:
            report_name = f"Rapport de non livrés du {date_from_str} au {date_to_str}"
        else:
            report_name = f"Rapport de non livrés du {date_from_str}"

        report = self.env['reliquat.report'].create({
            'name': report_name,
            'company_id': self.env.company.id,
            'active': True,
            'date_from': self.date_from,
            'date_to': self.date_to or self.date_from,
            'period_type': self.period_type,
        })

        if hasattr(report, 'generate_report_data'):
            report.generate_report_data()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Rapport de non livrés'),
            'res_model': 'reliquat.report',
            'res_id': report.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.onchange('period_type', 'date_from')
    def _onchange_dates(self):
        """Met à jour la date_to en fonction du type de période et de la date_from"""
        if not self.date_from:
            return

        if self.period_type == 'daily':
            self.date_to = self.date_from

        elif self.period_type == 'weekly':
            self.date_to = self.date_from + timedelta(days=6)

        elif self.period_type == 'biweekly':
            self.date_to = self.date_from + timedelta(days=13)

        elif self.period_type == 'monthly':
            self.date_to = self.date_from + relativedelta(months=1) - timedelta(days=1)

        elif self.period_type == 'quarterly':
            self.date_to = self.date_from + relativedelta(months=3) - timedelta(days=1)

        elif self.period_type == 'semiannual':
            self.date_to = self.date_from + relativedelta(months=6) - timedelta(days=1)

        elif self.period_type == 'yearly':
            self.date_to = self.date_from + relativedelta(years=1) - timedelta(days=1)

        elif self.period_type == 'custom':
            # Ne calcule rien, l'utilisateur choisit lui-même
            self.date_to = self.date_to or self.date_from


