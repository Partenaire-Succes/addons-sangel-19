# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class StockCasseReport(models.TransientModel):
    _name = 'stock.casse.report'
    _description = 'Rapport de casse'

    date_from = fields.Date(
        string='Date de début',
        required=True,
        default=fields.Date.context_today
    )
    date_to = fields.Date(
        string='Date de fin',
        required=True,
        default=fields.Date.context_today
    )
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
    )

    scrap_lines_ids = fields.Many2many(
        'stock.scrap',
        string='Lignes de casse',
        compute='_compute_scrap_lines_ids'
    )

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_scrap_lines_ids(self):
        for record in self:
            scraps = self.env['stock.scrap'].search([
                ('date_done', '>=', record.date_from),
                ('date_done', '<=', record.date_to),
                ('company_id', '=', record.company_id.id),
                ('state', '=', 'done'),
            ], order='date_done, name')
            # Consider 'CASSE' as scraps whose source location is not internal
        #    record.scrap_lines_ids = scraps.filtered(lambda s: s.location_id.usage != 'internal')
            record.scrap_lines_ids = scraps

    def action_print_report(self):
        self.ensure_one()
        if not self.scrap_lines_ids:
            raise UserError("Aucune donnée trouvée pour la période sélectionnée.")

        return self.env.ref('custom_reports.action_report_casse').report_action(self)

