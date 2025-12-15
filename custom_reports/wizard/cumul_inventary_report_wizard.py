from odoo import models, fields, api
from odoo.exceptions import UserError


class CumulInventaryReportWizard(models.TransientModel):
    _name = 'cumul.inventary.report.wizard'
    _description = 'Cumul Inventaire'

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
        default=lambda self: self.env.company
    )

    physical_lines_ids = fields.Many2many(
        'physical.inventory.line',
        string='Lignes physiques',
        compute='_compute_physical_lines_ids'
    )

    code_article_filter = fields.Char(
        string='Filtrer par Code Article',
        help='Laissez vide pour afficher tous les articles'
    )

    @api.depends('date_from', 'date_to', 'company_id', 'code_article_filter')
    def _compute_physical_lines_ids(self):
        for record in self:
            domain = [
                ('create_date', '>=', record.date_from),
                ('create_date', '<=', record.date_to),
                ('company_id', '=', record.company_id.id),
            ]

            # Filtrer par code article si spécifié
            if record.code_article_filter:
                domain.append(('code_article', 'ilike', record.code_article_filter))

            record.physical_lines_ids = self.env['physical.inventory.line'].search(
                domain,
                order='code_article, create_date'
            )

    @api.depends('physical_lines_ids')
    def _compute_grouped_data(self):
        """Grouper les données par article et calculer les totaux"""
        for record in self:
            grouped = {}
            for line in record.physical_lines_ids:
                key = (line.code_article, line.product_tmpl_id.id)
                if key not in grouped:
                    grouped[key] = {
                        'code_article': line.code_article,
                        'designation': line.product_tmpl_id.name,
                        'lines': [],
                        'total_ecart': 0.0,
                        'total_montant': 0.0,
                    }

                grouped[key]['lines'].append(line)
                grouped[key]['total_ecart'] += line.qty_diff or 0.0
                grouped[key]['total_montant'] += line.valorisation or 0.0

            record.grouped_data = str(grouped)

    def _get_grouped_lines(self):
        """
        Méthode pour grouper les lignes par article (code + désignation)
        Utilisée dans le template QWeb
        """
        self.ensure_one()
        grouped = {}

        for line in self.physical_lines_ids:
            # Créer une clé unique pour chaque article
            key = (line.code_article or '', line.product_tmpl_id.id)

            if key not in grouped:
                grouped[key] = {
                    'code_article': line.code_article or '',
                    'designation': line.product_tmpl_id.name or '',
                    'lines': [],
                    'total_ecart': 0.0,
                    'total_montant': 0.0,
                }

            grouped[key]['lines'].append(line)
            grouped[key]['total_ecart'] += line.qty_diff or 0.0
            grouped[key]['total_montant'] += line.valorisation or 0.0

        # Convertir en liste et trier par code article
        result = sorted(grouped.values(), key=lambda x: x['code_article'])
        return result

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise UserError("La date de début doit être antérieure à la date de fin.")

    def action_print_report(self):
        """Générer le rapport PDF"""
        return self.env.ref('custom_reports.action_report_cumul_inventaire').report_action(self)
