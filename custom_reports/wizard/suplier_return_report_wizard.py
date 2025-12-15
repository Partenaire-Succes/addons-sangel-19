from odoo import models, fields, api
from odoo.exceptions import UserError


class SupplierReturnReportWizard(models.TransientModel):
    _name = 'supplier.return.report.wizard'
    _description = 'Assistant Rapport Retours Fournisseurs'

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
    partner_ids = fields.Many2many(
        'res.partner',
        string='Fournisseurs',
        domain=[('supplier_rank', '>', 0)],
        help='Laissez vide pour tous les fournisseurs'
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise UserError("La date de début doit être antérieure à la date de fin.")

    def action_print_report(self):
        """Imprimer le rapport PDF"""
        self.ensure_one()
        return self.env.ref('custom_reports.action_report_supplier_returns').report_action(self)



    def _get_domain(self):
        """Construire le domaine pour filtrer les retours fournisseurs"""
        domain = [
            ('state', '=', 'done'),
            ('date_done', '>=', self.date_from),
            ('date_done', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('origin', '=like', 'Retour de%'),
        ]


        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))

        return domain

    def _get_report_data(self):
        """Récupérer et structurer les données du rapport"""
        pickings = self.env['stock.picking'].search(self._get_domain())


        # Grouper par fournisseur
        data_by_supplier = {}

        for picking in pickings:
            supplier = picking.partner_id
            if supplier not in data_by_supplier:
                data_by_supplier[supplier] = {
                    'supplier_name': supplier.name,
                    'returns': [],
                    'total_amount': 0.0,
                }

            # Calculer le montant total
            amount = sum(
                move.product_uom_qty * move.product_id.standard_price
                for move in picking.move_ids
            )

            data_by_supplier[supplier]['returns'].append({
                'date': picking.date_done,
                'reference': picking.name,
                'origin': picking.origin,
                'amount': amount,
                'moves': picking.move_ids,
            })
            data_by_supplier[supplier]['total_amount'] += amount

        return {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company': self.company_id,
            'suppliers': list(data_by_supplier.values()),
            'grand_total': sum(s['total_amount'] for s in data_by_supplier.values()),
        }
