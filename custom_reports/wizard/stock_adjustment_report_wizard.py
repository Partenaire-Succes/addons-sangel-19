from odoo import models, fields, api
from odoo.exceptions import UserError


class StockAdjustmentReportWizard(models.TransientModel):
    _name = 'stock.adjustment.report.wizard'
    _description = 'Ajustement de stock'

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

    scrap_lines_ids = fields.Many2many(
        'stock.scrap',
        string='Rébuts',
        compute='_compute_scrap_lines_ids'
    )

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_scrap_lines_ids(self):
        for record in self:
            record.scrap_lines_ids = self.env['stock.scrap'].search([
                ('date_done', '>=', record.date_from),
                ('date_done', '<=', record.date_to),
                ('company_id', '=', record.company_id.id),
                ('state', '=', 'done')
            ], order='date_done, name')

    def action_print_report(self):
        self.ensure_one()
        if not self.scrap_lines_ids:
            raise UserError("Aucune donnée trouvée pour la période sélectionnée.")

        return self.env.ref('custom_reports.action_report_stock_adjustment').report_action(self)

    def get_grouped_data(self):
        """Grouper les rebuts par type d'ajustement et raison"""
        self.ensure_one()

        grouped_data = {}

        for scrap in self.scrap_lines_ids:
            # Déterminer le type d'ajustement
            adjustment_type = self._get_adjustment_type(scrap)

            if adjustment_type not in grouped_data:
                grouped_data[adjustment_type] = {}

            # Grouper par raison
            reasons = scrap.scrap_reason_tag_ids
            if not reasons:
                reason_key = 'Sans raison'
                reason_name = 'Sans raison'
            else:
                # Utiliser toutes les raisons associées
                reason_key = ','.join(reasons.mapped('name'))
                reason_name = ', '.join(reasons.mapped('name'))

            if reason_key not in grouped_data[adjustment_type]:
                grouped_data[adjustment_type][reason_key] = {
                    'reason_name': reason_name,
                    'lines': []
                }

            grouped_data[adjustment_type][reason_key]['lines'].append({
                'document': scrap.name,
                'date': scrap.date_done,
                'cashier': scrap.create_uid.name,
                'article': scrap.product_id.code_article or '',
                'designation': scrap.product_id.name,
                'quantity': scrap.scrap_qty,
                'total_pa': scrap.scrap_qty * scrap.product_id.standard_price,
            })

        return grouped_data

    def _get_adjustment_type(self, scrap):
        """Déterminer le type d'ajustement basé sur la localisation ou d'autres critères"""
        # Logique pour déterminer le type (AUTOCONSOMMATION, CASSE, etc.)
        # À adapter selon vos besoins
        if scrap.location_id.usage == 'internal':
            return 'AUTOCONSOMMATION'
        else:
            return 'CASSE'

    def get_totals_by_type(self, grouped_data):
        """Calculer les totaux par type d'ajustement"""
        totals = {}
        for adj_type, reasons in grouped_data.items():
            total_qty = 0
            total_pa = 0
            for reason_data in reasons.values():
                for line in reason_data['lines']:
                    total_qty += line['quantity']
                    total_pa += line['total_pa']
            totals[adj_type] = {
                'quantity': total_qty,
                'total_pa': total_pa
            }
        return totals

    def get_grand_totals(self, totals):
        """Calculer les totaux généraux"""
        grand_total_qty = sum(t['quantity'] for t in totals.values())
        grand_total_pa = sum(t['total_pa'] for t in totals.values())
        return {
            'quantity': grand_total_qty,
            'total_pa': grand_total_pa
        }



