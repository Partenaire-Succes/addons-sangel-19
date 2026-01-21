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
            date_from = fields.Date.today() - timedelta(days=30)
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
        domain = [
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
            ('company_id', '=', self.env.company.id),
            ('state', 'in', ['sale', 'done'])
        ]
        orders = self.env['sale.order'].search(domain, limit=LIMIT, order="date_order desc")
        total = sum(self.env['sale.order'].search(domain).mapped('amount_total'))

        return {
            'orders': [{
                'name': o.name,
                'partner': o.partner_id.name,
                'date': o.date_order.strftime('%Y-%m-%d'),
                'amount': o.amount_total,
                'state': o.state,
            } for o in orders],
            'total': total,
            'count': self.env['sale.order'].search_count(domain),
            'domain': domain,
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
        orders = self.env['pos.order'].search(domain, limit=LIMIT, order="date_order desc")
        total = sum(self.env['pos.order'].search(domain).mapped('amount_total'))

        return {
            'orders': [{
                'name': o.name,
                'partner': o.partner_id.name or 'Client anonyme',
                'date': o.date_order.strftime('%Y-%m-%d %H:%M'),
                'amount': o.amount_total,
                'session': o.session_id.name,
            } for o in orders],
            'total': total,
            'count': self.env['pos.order'].search_count(domain),
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
        """Récupère les 5 meilleurs clients"""
        company_id = self.env.company.id
        
        # Ventes module vente
        query_sales = """
            SELECT partner_id, SUM(amount_total) as total
            FROM sale_order
            WHERE date_order >= %s AND date_order <= %s
            AND company_id = %s
            AND state IN ('sale', 'done')
            GROUP BY partner_id
        """
        
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
        
        self.env.cr.execute(query_sales, (date_from, date_to, company_id))
        sales_data = {row[0]: row[1] for row in self.env.cr.fetchall()}
        
        self.env.cr.execute(query_pos, (date_from, date_to, company_id))
        pos_data = {row[0]: row[1] for row in self.env.cr.fetchall()}
        
        # Combiner les données
        all_partners = {}
        for partner_id, amount in sales_data.items():
            all_partners[partner_id] = all_partners.get(partner_id, 0) + amount
        for partner_id, amount in pos_data.items():
            all_partners[partner_id] = all_partners.get(partner_id, 0) + amount
        
        # Trier et prendre les 5 premiers
        sorted_partners = sorted(all_partners.items(), key=lambda x: x[1], reverse=True)[:5]
        
        top_clients = []
        for partner_id, total in sorted_partners:
            partner = self.env['res.partner'].browse(partner_id)
            top_clients.append({
                'id': partner_id,
                'name': partner.name,
                'total': total,
                'ventes': sales_data.get(partner_id, 0),
                'pos': pos_data.get(partner_id, 0),
            })
        
        return top_clients

    def _get_statistiques(self, date_from, date_to):
        """Calcule les statistiques globales"""
        ventes = self._get_ventes_demi_gros(date_from, date_to)
        pos = self._get_ventes_pos_demi(date_from, date_to)
        achats = self._get_achats_commande(date_from, date_to)
        
        total_revenus = ventes['total'] + pos['total']
        marge_brute = total_revenus - achats['total']
        taux_marge = (marge_brute / total_revenus * 100) if total_revenus > 0 else 0
        
        return {
            'total_ventes': ventes['total'],
            'total_pos': pos['total'],
            'total_achats': achats['total'],
            'total_revenus': total_revenus,
            'marge_brute': marge_brute,
            'taux_marge': round(taux_marge, 2),
            'nb_commandes_ventes': ventes['count'],
            'nb_commandes_pos': pos['count'],
            'nb_commandes_achats': achats['count'],
        }

    def _get_evolution_ventes(self, date_from, date_to):
        """Récupère l'évolution des ventes par jour"""
        company_id = self.env.company.id
        
        query = """
            SELECT DATE(date_order) as date, 
                   SUM(amount_total) as ventes,
                   0 as pos
            FROM sale_order
            WHERE date_order >= %s AND date_order <= %s
            AND company_id = %s
            AND state IN ('sale', 'done')
            GROUP BY DATE(date_order)
            
            UNION ALL
            
            SELECT DATE(date_order) as date,
                   0 as ventes,
                   SUM(amount_total) as pos
            FROM pos_order
            WHERE date_order >= %s AND date_order <= %s
            AND company_id = %s
            AND state IN ('paid', 'done', 'invoiced')
            GROUP BY DATE(date_order)
            
            ORDER BY date
        """
        
        self.env.cr.execute(query, (date_from, date_to, company_id, date_from, date_to, company_id))
        results = self.env.cr.fetchall()
        
        # Agréger par date
        evolution = {}
        for date, ventes, pos in results:
            date_str = date.strftime('%Y-%m-%d')
            if date_str not in evolution:
                evolution[date_str] = {'date': date_str, 'ventes': 0, 'pos': 0}
            evolution[date_str]['ventes'] += ventes
            evolution[date_str]['pos'] += pos
        
        return list(evolution.values())