from odoo import models, fields, api
from datetime import datetime, timedelta
import locale


class ReportDailySalesWizard(models.TransientModel):
    _name = 'report.daily.sales.wizard'
    _description = 'Rapport Journalier des Ventes'

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
    report_type = fields.Selection([
        ('sale', 'Ventes (Sales)'),
        ('pos', 'Point de Vente (POS)'),
    ], string='Source', required=True, default='sale')

    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company
    )

    def action_print_report(self):
        return self.env.ref('custom_reports.action_report_daily_sales').report_action(self)

    def get_daily_sales(self):
        """Récupère les ventes journalières avec jours en français"""
        data = []
        current_date = self.date_from
        delta = timedelta(days=1)

        # ✅ Forcer le format de date français
        try:
            locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
        except locale.Error:
            try:
                locale.setlocale(locale.LC_TIME, 'fr_FR')
            except locale.Error:
                pass  # Si aucune locale française n'est disponible

        while current_date <= self.date_to:
            jour = current_date.strftime('%a').capitalize()  # ex: 'Lun', 'Mar', 'Mer'
            next_day = current_date + delta

            if self.report_type == 'sale':
                orders = self.env['sale.order'].search([
                    ('date_order', '>=', fields.Datetime.to_datetime(current_date)),
                    ('date_order', '<', fields.Datetime.to_datetime(next_day)),
                    ('state', 'in', ['sale', 'done']),
                    ('company_id', '=', self.company_id.id),
                ])
                order_lines = self.env['sale.order.line'].search([
                    ('order_id', 'in', orders.ids),
                    ('state', '!=', 'cancel')
                ])

                ca_ht = sum(order.amount_untaxed for order in orders)
                ca_ttc = sum(order.amount_total for order in orders)

                # ✅ CORRECTION : Calcul de la marge réelle (prix de vente - coût d'achat)
                cout_total = sum(
                    line.product_uom_qty * line.product_id.standard_price
                    for line in order_lines
                )
                marge = ca_ht - cout_total  # Marge = CA HT - Coût d'achat

                remises = sum(
                    (l.price_unit * l.product_uom_qty * (l.discount or 0.0) / 100.0)
                    for l in order_lines
                )
                nb_clients = len(set(orders.mapped('partner_id.id')))

            else:  # POS
                orders = self.env['pos.order'].search([
                    ('date_order', '>=', fields.Datetime.to_datetime(current_date)),
                    ('date_order', '<', fields.Datetime.to_datetime(next_day)),
                    ('state', 'in', ['paid', 'invoiced', 'done']),
                    ('company_id', '=', self.company_id.id),
                ])
                order_lines = self.env['pos.order.line'].search([
                    ('order_id', 'in', orders.ids)
                ])

                # ✅ CORRECTION : Récupérer le CA HT depuis les commandes POS
                ca_ht = sum(order.amount_tax == 0 and order.amount_total or
                            (order.amount_total - order.amount_tax) for order in orders)
                ca_ttc = sum(order.amount_total for order in orders)

                # ✅ CORRECTION : Calcul de la marge réelle pour POS
                cout_total = sum(
                    line.qty * line.product_id.standard_price
                    for line in order_lines
                )
                marge = ca_ht - cout_total

                remises = sum(
                    (l.price_unit * l.qty * (l.discount or 0.0) / 100.0)
                    for l in order_lines
                )
                nb_clients = len(set(orders.mapped('partner_id.id')))

            panier_valeur = ca_ttc / nb_clients if nb_clients else 0
            panier_qte = (
                sum(order_lines.mapped('product_uom_qty' if self.report_type == 'sale' else 'qty'))
                / nb_clients if nb_clients else 0
            )
            # ✅ CORRECTION : Le % de marge est calculé sur le CA HT, pas le CA TTC
            pct_marge = (marge / ca_ht * 100.0) if ca_ht else 0.0

            data.append({
                'jour': jour,
                'date': current_date,
                'ca_ht': ca_ht,
                'ca_ttc': ca_ttc,
                'marge': marge,
                'pct_marge': pct_marge,
                'nb_clients': nb_clients,
                'panier_valeur': panier_valeur,
                'panier_qte': panier_qte,
                'remises': remises,
                'meteo': '',
                'obs': '',
            })

            current_date = next_day

        return data

    def get_totaux(self, lignes):
        """Calcule les totaux et moyennes"""
        if not lignes:
            return {}
        n = len(lignes)

        total_ca_ht = sum(l['ca_ht'] for l in lignes)
        total_ca_ttc = sum(l['ca_ttc'] for l in lignes)
        total_marge = sum(l['marge'] for l in lignes)

        return {
            'ca_ht': total_ca_ht,
            'ca_ttc': total_ca_ttc,
            'marge': total_marge,
            'pct_marge': (total_marge / total_ca_ht * 100.0) if total_ca_ht else 0.0,
            'nb_clients': sum(l['nb_clients'] for l in lignes),
            'panier_valeur': sum(l['panier_valeur'] for l in lignes) / n,
            'panier_qte': sum(l['panier_qte'] for l in lignes) / n,
            'remises': sum(l['remises'] for l in lignes),
        }