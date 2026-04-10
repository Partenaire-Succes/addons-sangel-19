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
        ('all', 'Vente et Point de vente')
    ], string='Source', required=True, default='all')

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

        # Forcer le format de date français
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
            refund_ht = refund_ttc = 0.0

            refunds = self.env['account.move'].search([
                    ('invoice_date', '>=', fields.Date.to_date(current_date)),
                    ('invoice_date', '<', fields.Date.to_date(next_day)),
                    ('move_type', '=', 'out_refund'),
                    ('pos_order_ids', '=', False),  # Exclure les remboursements liés à des commandes POS
                    ('state', '=', 'posted'),
                    ('company_id', '=', self.company_id.id),
                ])
            if refunds:
                # Si des remboursements existent, on les exclut du calcul du CA
                refund_ht = sum(refunds.mapped('amount_untaxed'))
                refund_ttc = sum(refunds.mapped('amount_total'))

            if self.report_type == 'sale':
                # orders = self.env['sale.order'].search([
                #     ('date_order', '>=', fields.Datetime.to_datetime(current_date)),
                #     ('date_order', '<', fields.Datetime.to_datetime(next_day)),
                #     ('state', 'in', ['sale', 'done']),
                #     ('invoice_ids.move_type', '=', 'out_invoice'),
                #     ('invoice_ids.state', '=', 'posted'),
                #     ('company_id', '=', self.company_id.id),
                # ])
                moves = self.env['account.move'].search([
                    ('invoice_date', '>=', fields.Date.to_date(current_date)),
                    ('invoice_date', '<', fields.Date.to_date(next_day)),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('pos_order_ids', '=', False),  # Exclure les factures liées à des commandes POS
                    ('company_id', '=', self.company_id.id),
                ])

                # order_lines = self.env['sale.order.line'].search([
                #     ('order_id', 'in', orders.ids),
                #     ('state', '!=', 'cancel')
                # ])
                order_lines = self.env['account.move.line'].search([
                    ('move_id', 'in', moves.ids)
                ])

                ca_ht = sum(order.amount_untaxed for order in orders) - refund_ht
                ca_ttc = sum(order.amount_total for order in orders) - refund_ttc
                cout_total = sum(
                    line.quantity * line.product_id.standard_price
                    for line in order_lines
                )
                marge = ca_ht - cout_total
                remises = 0.0
                remise_line = sum(
                    l.price_unit * l.quantity * (l.discount or 0.0) / 100.0
                    for l in order_lines
                )
                remise_global = sum(
                    l.price_unit * l.quantity
                    for l in order_lines
                    if l.price_unit < 0
                )
                remises = remise_line - remise_global
                nb_clients = len(orders)
                # FIX 4 : champ correct pour panier_qte
                total_qte = sum(
                    line.quantity
                    for line in order_lines
                    if line.price_unit >= 0
                )

            elif self.report_type == 'pos':
                orders = self.env['pos.order'].search([
                    ('date_order', '>=', fields.Datetime.to_datetime(current_date)),
                    ('date_order', '<', fields.Datetime.to_datetime(next_day)),
                    ('state', 'in', ['paid', 'invoiced', 'done']),
                    ('company_id', '=', self.company_id.id),
                ])
                order_lines = self.env['pos.order.line'].search([
                    ('order_id', 'in', orders.ids)
                ])

                # FIX 3 : remplacer le and/or par un vrai ternaire
                ca_ht = sum(
                    order.amount_total if order.amount_tax == 0
                    else (order.amount_total - order.amount_tax)
                    for order in orders
                ) - refund_ht
                ca_ttc = sum(order.amount_total for order in orders) - refund_ttc
                cout_total = sum(
                    line.qty * line.product_id.standard_price
                    for line in order_lines
                )
                marge = ca_ht - cout_total
                remises = 0.0
                remise_line = sum(
                    l.price_unit * l.qty * (l.discount or 0.0) / 100.0
                    for l in order_lines
                )
                remise_global = sum(
                    l.price_unit * l.qty
                    for l in order_lines
                    if l.price_unit < 0
                )
                remises = remise_line - remise_global
                nb_clients = len(orders)
                total_qte = sum(
                    line.qty
                    for line in order_lines
                    if line.price_unit >= 0
                )

            else:  # 'all' : ventes + POS combinés
                # --- Ventes ---
                # sale_orders = self.env['sale.order'].search([
                #     ('date_order', '>=', fields.Datetime.to_datetime(current_date)),
                #     ('date_order', '<', fields.Datetime.to_datetime(next_day)),
                #     ('state', 'in', ['sale', 'done']),
                #     ('company_id', '=', self.company_id.id),
                # ])
                # sale_order_lines = self.env['sale.order.line'].search([
                #     ('order_id', 'in', sale_orders.ids),
                #     ('state', '!=', 'cancel')
                # ])

                sale_moves = self.env['account.move'].search([
                    ('invoice_date', '>=', fields.Date.to_date(current_date)),
                    ('invoice_date', '<', fields.Date.to_date(next_day)),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted'),
                    ('pos_order_ids', '=', False),  # Exclure les factures liées à des commandes POS
                    ('company_id', '=', self.company_id.id),
                ])

                sale_order_lines = self.env['account.move.line'].search([
                    ('move_id', 'in', sale_moves.ids),
                ])


                sale_ca_ht = sum(order.amount_untaxed for order in sale_moves)
                sale_ca_ttc = sum(order.amount_total for order in sale_moves)
                sale_cout_total = sum(
                    line.quantity * line.product_id.standard_price
                    for line in sale_order_lines
                )
                sale_marge = sale_ca_ht - sale_cout_total
                sale_remises = 0.0
                sale_remise_line = sum(
                    l.price_unit * l.quantity * (l.discount or 0.0) / 100.0
                    for l in sale_order_lines
                )
                sale_remise_global = sum(
                    l.price_unit * l.quantity
                    for l in sale_order_lines
                    if l.price_unit < 0
                )
                sale_remises = sale_remise_line - sale_remise_global
                sale_qte = sum(
                    line.quantity
                    for line in sale_order_lines
                    if line.price_unit >= 0
                )

                # --- POS ---
                pos_orders = self.env['pos.order'].search([
                    ('date_order', '>=', fields.Datetime.to_datetime(current_date)),
                    ('date_order', '<', fields.Datetime.to_datetime(next_day)),
                    ('state', 'in', ['paid', 'invoiced', 'done']),
                    ('company_id', '=', self.company_id.id),
                ])
                pos_order_lines = self.env['pos.order.line'].search([
                    ('order_id', 'in', pos_orders.ids)
                ])
                # FIX 3 : ternaire propre
                pos_ca_ht = sum(
                    order.amount_total if order.amount_tax == 0
                    else (order.amount_total - order.amount_tax)
                    for order in pos_orders
                )
                pos_ca_ttc = sum(order.amount_total for order in pos_orders)
                pos_cout_total = sum(
                    line.qty * line.product_id.standard_price
                    for line in pos_order_lines
                )
                pos_marge = pos_ca_ht - pos_cout_total
                pos_remises = 0.0
                pos_remise_line = sum(
                    l.price_unit * l.qty * (l.discount or 0.0) / 100.0
                    for l in pos_order_lines
                )
                pos_remise_global = sum(
                    l.price_unit * l.qty
                    for l in pos_order_lines
                    if l.price_unit < 0
                )
                pos_remises = pos_remise_line - pos_remise_global
                pos_qte = sum(
                    line.qty
                    for line in pos_order_lines
                    if line.price_unit >= 0
                )

                # FIX 1 : ca_ht défini dans le bloc else
                ca_ht = sale_ca_ht + pos_ca_ht - refund_ht
                ca_ttc = sale_ca_ttc + pos_ca_ttc - refund_ttc
                marge = sale_marge + pos_marge
                remises = sale_remises + pos_remises
                nb_clients = len(sale_moves) + len(pos_orders)
                # FIX 2 : total_qte calculé sans .mapped() sur une liste
                total_qte = sale_qte + pos_qte

            panier_valeur = ca_ttc / nb_clients if nb_clients else 0
            panier_qte = total_qte / nb_clients if nb_clients else 0
            # % de marge calculé sur le CA HT
            pct_marge = (marge / ca_ht * 100.0) if ca_ht else 0.0

            # Budget journalier : lignes dont le parent est en cours ou terminé
            budget_lines = self.env['daily.budget.analytic.line'].search([
                ('daily_budget_id.state', 'in', ['in_progress', 'done']),
                ('daily_budget_id.company_id', '=', self.company_id.id),
                ('date_from', '>=', fields.Datetime.to_datetime(current_date)),
                ('date_from', '<', fields.Datetime.to_datetime(next_day)),
            ])
            budget = sum(budget_lines.mapped('budget_amount'))
            budget_marge = sum(budget_lines.mapped('budget_marge'))

            data.append({
                'jour': jour,
                'date': current_date,
                'ca_ht': ca_ht,
                'ca_ttc': ca_ttc,
                'budget': budget,
                'budget_marge': budget_marge,
                'marge': marge,
                'pct_marge': pct_marge,
                'nb_clients': nb_clients,
                'panier_valeur': panier_valeur,
                'panier_qte': panier_qte,
                'remises': remises,
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
            'budget': sum(l['budget'] for l in lignes),
            'budget_marge': sum(l['budget_marge'] for l in lignes),
            'marge': total_marge,
            'pct_marge': (total_marge / total_ca_ht * 100.0) if total_ca_ht else 0.0,
            'nb_clients': sum(l['nb_clients'] for l in lignes),
            'panier_valeur': sum(l['panier_valeur'] for l in lignes) / n,
            'panier_qte': sum(l['panier_qte'] for l in lignes) / n,
            'remises': sum(l['remises'] for l in lignes),
        }