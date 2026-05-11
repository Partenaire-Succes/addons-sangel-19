# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class RapportValidationWizard(models.TransientModel):
    _name = 'rapport.validation.wizard'
    _description = 'Rapport des validations manager POS'

    date_from = fields.Date('Du', required=True, default=fields.Date.context_today)
    date_to = fields.Date('Au', required=True, default=fields.Date.context_today)
    config_ids = fields.Many2many(
        'pos.config', string='Caisses',
        help="Laisser vide pour inclure toutes les caisses."
    )
    # Sessions calculées lors de la génération — passées au template en un seul document
    session_ids = fields.Many2many('pos.session', string='Sessions du rapport')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise UserError("La date de début doit être antérieure ou égale à la date de fin.")

    def action_generate_report(self):
        domain = [
            ('start_at', '>=', fields.Datetime.from_string(str(self.date_from) + ' 00:00:00')),
            ('start_at', '<=', fields.Datetime.from_string(str(self.date_to) + ' 23:59:59')),
        ]
        if self.config_ids:
            domain.append(('config_id', 'in', self.config_ids.ids))

        sessions = self.env['pos.session'].search(domain, order='start_at asc')
        if not sessions:
            raise UserError(
                "Aucune session trouvée pour la période sélectionnée%s." % (
                    " et les caisses choisies" if self.config_ids else ""
                )
            )

        # Stocker les sessions sur le wizard pour le template ; passer self (1 seul doc)
        self.session_ids = sessions
        return self.env.ref('custom_pos.action_report_validation_log').report_action(self)
