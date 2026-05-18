from odoo import models, fields, api
from datetime import timedelta

LIMIT = 5

class DashboardManagementAdmin(models.Model):
    _name = 'dashboard.management.admin'
    _description = 'Dashboard Management Administration Data'

    company_id = fields.Many2one('res.company', 
                                 string='Company', 
                                 default=lambda self: self.env.company)

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        if not date_from:
            today = fields.Date.today()
            date_from = today.replace(day=1)  # Premier jour du mois en cours
        if not date_to:
            date_to = fields.Date.today()

        return {
            'ventes_demi_gros': self._get_ventes_demi_gros(date_from, date_to),
            'ventes_pos_demi': self._get_ventes_pos_demi(date_from, date_to),
            'achats_commande': self._get_achats_commande(date_from, date_to),
            'top_clients': self._get_top_clients(date_from, date_to),
            'statistiques': self._get_statistiques(date_from, date_to),
            'evolution_ventes': self._get_evolution_ventes(date_from, date_to),
        }

    # ------------------ VENTES ------------------
    def _get_ventes_demi_gros(self, date_from, date_to):
        # Factures validées dans la période (hors POS)
        moves = self.env['account.move'].search([
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('pos_order_ids', '=', False),
            ('company_id', '=', self.env.company.id),
        ])
        invoice_domain = [('invoice_ids', 'in', moves.ids)]
        all_orders = self.env['sale.order'].search(invoice_domain)
        orders = self.env['sale.order'].search(invoice_domain, limit=LIMIT, order='date_order desc')

        # Avoirs validés sur la période (hors POS)
        refunds = self.env['account.move'].search([
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('pos_order_ids', '=', False),
            ('company_id', '=', self.env.company.id),
        ])
        refund_ht = sum(refunds.mapped('amount_untaxed'))
        refund_ttc = sum(refunds.mapped('amount_total'))

        total = sum(all_orders.mapped('amount_total')) - refund_ttc
        total_ht = sum(all_orders.mapped('amount_untaxed')) - refund_ht
        marge = sum(all_orders.mapped('margin'))
        marge_percent = round(marge / total_ht * 100, 2) if total_ht else 0

        return {
            'orders': [{
                'name': o.name,
                'partner': o.partner_id.name,
                'date': o.date_order.strftime('%Y-%m-%d'),
                'amount': o.amount_total,
                'state': o.state,
                'marge': o.margin,
                'marge_percent': round(o.margin / o.amount_untaxed * 100 if o.amount_untaxed else 0, 2),
            } for o in orders],
            'total': total,
            'count': len(all_orders),
            'marge': marge,
            'marge_percent': marge_percent,
            'domain': invoice_domain,
            'model': 'sale.order',
        }

    # ------------------ POS ------------------
    def _get_ventes_pos_demi(self, date_from, date_to):
        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
            ('company_id', '=', self.env.company.id),
            ('state', 'in', ['paid', 'done', 'invoiced'])
        ]
        all_orders = self.env['pos.order'].search(domain)
        orders = self.env['pos.order'].search(domain, limit=LIMIT, order='date_order desc')

        total = sum(all_orders.mapped('amount_total'))
        marge = sum(all_orders.mapped('margin'))
        marge_percent = round(marge / total * 100, 2) if total else 0

        return {
            'orders': [{
                'name': o.name,
                'partner': o.partner_id.name or 'Client anonyme',
                'date': o.date_order.strftime('%Y-%m-%d %H:%M'),
                'amount': o.amount_total,
                'session': o.session_id.name,
                'marge': o.margin,
                'marge_percent': round(o.margin / o.amount_total * 100 if o.amount_total else 0, 2),
            } for o in orders],
            'total': total,
            'count': len(all_orders),
            'marge': marge,
            'marge_percent': marge_percent,
            'domain': domain,
            'model': 'pos.order',
        }

    # ------------------ ACHATS ------------------
    def _get_achats_commande(self, date_from, date_to):
        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
            ('company_id', '=', self.env.company.id),
            ('state', 'in', ['purchase', 'done'])
        ]
        orders = self.env['purchase.order'].search(domain, limit=LIMIT, order="date_order desc")
        total = sum(self.env['purchase.order'].search(domain).mapped('amount_total'))

        return {
            'orders': [{
                'name': o.name,
                'partner': o.partner_id.name,
                'date': o.date_order.strftime('%Y-%m-%d'),
                'amount': o.amount_total,
                'state': o.state,
            } for o in orders],
            'total': total,
            'count': self.env['purchase.order'].search_count(domain),
            'domain': domain,
            'model': 'purchase.order',
        }
    
    def _get_top_clients(self, date_from, date_to):
        company_id = self.env.company.id

        # Ventes via factures validées
        moves = self.env['account.move'].search([
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('pos_order_ids', '=', False),
            ('company_id', '=', company_id),
        ])
        sale_orders = self.env['sale.order'].search([('invoice_ids', 'in', moves.ids)])
        sales_data = {}
        for o in sale_orders:
            if o.partner_id.id:
                pid = o.partner_id.id
                sales_data[pid] = sales_data.get(pid, 0) + o.amount_total

        # Ventes POS
        query_pos = """
            SELECT partner_id, SUM(amount_total) as total
            FROM pos_order
            WHERE date_order >= %s AND date_order <= %s
            AND company_id = %s
            AND state IN ('paid', 'done', 'invoiced')
            AND partner_id IS NOT NULL
            GROUP BY partner_id
        """
        self.env.cr.execute(query_pos, (date_from, date_to, company_id))
        pos_data = {row[0]: row[1] for row in self.env.cr.fetchall()}

        all_partners = {}
        for pid, amount in sales_data.items():
            all_partners[pid] = all_partners.get(pid, 0) + amount
        for pid, amount in pos_data.items():
            all_partners[pid] = all_partners.get(pid, 0) + amount

        sorted_partners = sorted(all_partners.items(), key=lambda x: x[1], reverse=True)[:5]

        return [{
            'id': pid,
            'name': self.env['res.partner'].browse(pid).name,
            'total': total,
            'ventes': sales_data.get(pid, 0),
            'pos': pos_data.get(pid, 0),
        } for pid, total in sorted_partners]

    
    def _get_statistiques(self, date_from, date_to):
        """Calcule les statistiques globales"""
        ventes = self._get_ventes_demi_gros(date_from, date_to)
        pos = self._get_ventes_pos_demi(date_from, date_to)
        achats = self._get_achats_commande(date_from, date_to)

        total_revenus = ventes['total'] + pos['total']
        marge_brute = ventes['marge'] + pos['marge']
        taux_marge = round(marge_brute / total_revenus * 100, 2) if total_revenus > 0 else 0,

        return {
            'total_ventes': ventes['total'],
            'total_pos': pos['total'],
            'total_achats': achats['total'],
            'total_revenus': total_revenus,
            'marge_brute': marge_brute,
            'taux_marge': taux_marge,
            'marge_ventes': ventes['marge'],
            'marge_pos': pos['marge'],
            'marge_pos_percent': pos['marge_percent'],
            'marge_ventes_percent': ventes['marge_percent'],
            'nb_commandes_ventes': ventes['count'],
            'nb_commandes_pos': pos['count'],
            'nb_commandes_achats': achats['count'],
        }

    def _get_evolution_ventes(self, date_from, date_to):
        company_id = self.env.company.id

        # Ventes via factures validées, groupées par invoice_date
        sale_moves = self.env['account.move'].search([
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('pos_order_ids', '=', False),
            ('company_id', '=', company_id),
        ])
        sales_by_date = {}
        for move in sale_moves:
            date_str = move.invoice_date.strftime('%Y-%m-%d')
            sales_by_date[date_str] = sales_by_date.get(date_str, 0) + move.amount_total

        # POS par date_order
        query_pos = """
            SELECT DATE(date_order) as date, SUM(amount_total) as pos
            FROM pos_order
            WHERE date_order >= %s AND date_order <= %s
            AND company_id = %s
            AND state IN ('paid', 'done', 'invoiced')
            GROUP BY DATE(date_order)
        """
        self.env.cr.execute(query_pos, (date_from, date_to, company_id))
        pos_by_date = {row[0].strftime('%Y-%m-%d'): row[1] for row in self.env.cr.fetchall()}

        all_dates = set(sales_by_date.keys()) | set(pos_by_date.keys())
        return [
            {'date': d, 'ventes': sales_by_date.get(d, 0), 'pos': pos_by_date.get(d, 0)}
            for d in sorted(all_dates)
        ]