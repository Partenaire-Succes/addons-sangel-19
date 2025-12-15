from odoo import models, fields, api
from odoo.exceptions import UserError


class ReceptionFournisseurWizard(models.TransientModel):
    _name = 'reception.fournisseur.wizard'
    _description = 'Wizard Rapport Réceptions Fournisseurs'

    date_debut = fields.Date(
        string='Date de début',
        required=True,
        default=fields.Date.context_today
    )
    date_fin = fields.Date(
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

    fournisseur_ids = fields.Many2many(
        'res.partner',
        string='Fournisseurs',
        domain=[('supplier_rank', '>', 0)],
        help='Laissez vide pour inclure tous les fournisseurs'
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id,
    )



    @api.constrains('date_debut', 'date_fin')
    def _check_dates(self):
        for record in self:
            if record.date_debut > record.date_fin:
                raise UserError("La date de début doit être antérieure à la date de fin.")

    def _get_pickings_data(self):
        """Récupère et organise les données des réceptions par fournisseur"""
        self.ensure_one()

        domain = [
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
            ('date_done', '>=', self.date_debut),
            ('date_done', '<=', self.date_fin),
            ('company_id', '=', self.company_id.id),
        ]

        if self.fournisseur_ids:
            domain.append(('partner_id', 'in', self.fournisseur_ids.ids))

        pickings = self.env['stock.picking'].search(domain, order='partner_id, date_done')

        if not pickings:
            raise UserError("Aucune réception trouvée pour la période sélectionnée.")

        # Grouper par fournisseur
        fournisseurs_data = {}

        for picking in pickings:
            partner = picking.partner_id
            if partner.id not in fournisseurs_data:
                fournisseurs_data[partner.id] = {
                    'partner': partner,
                    'receptions': [],
                    'total': 0.0
                }

            total_reception = 0.0

            for move in picking.move_ids_without_package:
                if move.purchase_line_id:
                    total_reception = move.purchase_line_id.order_id.amount_total

            fournisseurs_data[partner.id]['receptions'].append({
                'type': picking.picking_type_id.name[:3].upper(),
                'date': picking.date_done,
                'numero': picking.name,
                'ref': picking.origin or '',
                'total': total_reception
            })

            fournisseurs_data[partner.id]['total'] += total_reception

        return list(fournisseurs_data.values())

    def action_print_report(self):
        """Génère le rapport PDF"""
        self.ensure_one()

        # Vérifier qu'il y a des données
        data = self._get_pickings_data()

        return self.env.ref('custom_reports.action_report_reception_fournisseur').report_action(self)
