from odoo import models, fields, api
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError


class ReliquatReport(models.Model):
    _name = 'reliquat.report'
    _inherit = ['mail.thread','mail.activity.mixin']
    _description = 'Rapport de non livrés'
    _order = 'date_from desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Nom du rapport',
        required=True,
        default=lambda self: self._get_default_name()
    )

    active = fields.Boolean(
        string='Actif',
        default=True
    )

    date_from = fields.Date(
        string='Date de début',
        required=True
    )

    date_to = fields.Date(
        string='Date de fin',
        required=True
    )

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

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmé'),
        ('printed', 'Imprimé')
    ], string='État', default='draft')

    # Lignes de non livrés
    line_ids = fields.One2many(
        comodel_name='reliquat.report.line',
        inverse_name='report_id',
        string='Lignes de non livrés'
    )

    total_orders = fields.Integer(
        string='Nombre decommandes',
        compute='_compute_statistics'
    )

    total_qty_ordered = fields.Float(
        string='Quantité totale commandée',
        compute='_compute_statistics'
    )

    total_qty_received = fields.Float(
        string='Quantité totale reçue',
         compute='_compute_statistics'
    )

    total_qty_pending = fields.Float(
        string='Quantité en attente',
        compute='_compute_statistics'
    )

    satisfaction_rate = fields.Float(
        string='Taux de satisfaction',
        compute='_compute_statistics'
    )

    created_by = fields.Many2one(
        comodel_name='res.users',
        string='Créé par',
        default=lambda self: self.env.user
    )

    creation_date = fields.Datetime(
        string='Date de création',
        default=fields.Datetime.now
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Société',
        default=lambda self: self.env.company
    )

    @api.model
    def _get_default_name(self):
        """Construit le nom par défaut avec les dates en jj/mm/aaaa"""

        if not self.date_from:
            raise ValueError(_("Veuillez définir la date de début."))

        date_from_str = self.date_from.strftime('%d/%m/%Y')
        date_to_str = self.date_to.strftime('%d/%m/%Y') if self.date_to else None

        if self.date_to and self.date_from != self.date_to:
            report_name = f"Rapport de non livrés du {date_from_str} au {date_to_str}"
        else:
            report_name = f"Rapport de non livrés du {date_from_str}"

    @api.onchange('date_from', 'date_to')
    def _onchange_dates(self):
        """Met à jour automatiquement le nom si les deux dates sont définies"""
        if self.date_from and self.date_to:
            date_from_str = self.date_from.strftime('%d/%m/%Y')
            date_to_str = self.date_to.strftime('%d/%m/%Y')
            self.name = f"Rapport de non livrés du {date_from_str} au {date_to_str}"

    @api.depends('line_ids')
    def _compute_statistics(self):
        for report in self:
            if report.line_ids:
                report.total_orders = len(report.line_ids)
                report.total_qty_ordered = sum(line.qty_ordered for line in report.line_ids)
                report.total_qty_received = sum(line.qty_received for line in report.line_ids)
                report.total_qty_pending = report.total_qty_ordered - report.total_qty_received

                if report.total_qty_ordered > 0:
                    report.satisfaction_rate = report.total_qty_received / report.total_qty_ordered
                else:
                    report.satisfaction_rate = 0.0
            else:
                report.total_orders = 0
                report.total_qty_ordered = 0.0
                report.total_qty_received = 0.0
                report.total_qty_pending = 0.0
                report.satisfaction_rate = 0.0

    def generate_report_data(self):
        """Génère les données du rapport basé sur les commandes d'achat"""
        self.ensure_one()

        # Supprimer les anciennes lignes
        self.line_ids.unlink()

        # Rechercher les commandes d'achat dans la période
        purchase_orders = self.env['purchase.order'].search([
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('state', 'in', ['purchase', 'done'])
        ])

        lines_data = []
        for order in purchase_orders:
            for line in order.order_line:
                qty_received = sum(move.quantity for move in line.move_ids
                                   if move.state == 'done')

                qty_pending = line.product_qty - qty_received

                if qty_pending > 0:  # Seulement les lignes avec reliquats
                    satisfaction_rate = qty_received / line.product_qty if line.product_qty > 0 else 0

                    lines_data.append({
                        'report_id': self.id,
                        'purchase_order_id': order.id,
                        'partner_id': order.partner_id.id,
                        'product_id': line.product_id.id,
                        'qty_ordered': line.product_qty,
                        'qty_received': qty_received,
                        'qty_pending': qty_pending,
                        'satisfaction_rate': satisfaction_rate,
                        'order_date': order.date_order,
                    })

        # Créer les lignes
        self.env['reliquat.report.line'].create(lines_data)

        return True


    def action_print(self):
        self.state = 'printed'
        return self.env.ref('custom_reliquat_report.action_report_reliquat').report_action(self)



