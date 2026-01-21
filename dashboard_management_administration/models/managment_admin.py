# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaire Succes Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com>)
#    Author: Adama KONE
#
#############################################################################
from odoo import api, fields, models, _


class ManagmentAdmin(models.Model):
    _name = 'managment.admin'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _description = 'Gestion d administration pour le resposnable'

    name = fields.Char(string='Nom', required=False)
    responsible_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user, required=True)
    date_from = fields.Date(string='Date de début', required=True)
    date_to = fields.Date(string='Date de fin', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    pos_order_ids = fields.One2many('pos.order', 'managment_admin_id', string='Commandes POS')
    sale_order_ids = fields.One2many('sale.order', 'managment_admin_id', string='Commandes Vente')
    purchase_order_ids = fields.One2many('purchase.order', 'managment_admin_id', string='Commandes Achat')

    @api.model
    def get_grouped_data(self, date_from=None, date_to=None):
        """Récupère les données groupées par période"""
        if not date_from or not date_to:
            return {
                'ventes_groupees': [],
                'achats_groupes': [],
                'pos_groupes': []
            }

        return {
            'ventes_groupees': self._get_ventes_groupees(date_from, date_to),
            'achats_groupes': self._get_achats_groupes(date_from, date_to),
            'pos_groupes': self._get_pos_groupes(date_from, date_to),
        }

    def _get_ventes_groupees(self, date_from, date_to):
        """Groupe les ventes par intervalle de date"""
        company_id = self.env.company.id
        
        query = """
            SELECT 
                %s as date_from,
                %s as date_to,
                COUNT(*) as nb_commandes,
                SUM(amount_total) as montant_total
            FROM sale_order
            WHERE date_order >= %s 
            AND date_order <= %s
            AND company_id = %s
            AND state IN ('sale', 'done')
        """
        
        self.env.cr.execute(query, (date_from, date_to, date_from, date_to, company_id))
        result = self.env.cr.fetchone()
        
        if result and result[2] > 0:  # Si au moins une commande
            return [{
                'date_from': result[0],
                'date_to': result[1],
                'nb_commandes': result[2],
                'montant_total': result[3],
                'domain': [
                    ('date_order', '>=', date_from),
                    ('date_order', '<=', date_to),
                    ('company_id', '=', company_id),
                    ('state', 'in', ['sale', 'done'])
                ],
                'model': 'sale.order',
            }]
        return []

    def _get_achats_groupes(self, date_from, date_to):
        """Groupe les achats par intervalle de date"""
        company_id = self.env.company.id
        
        query = """
            SELECT 
                %s as date_from,
                %s as date_to,
                COUNT(*) as nb_commandes,
                SUM(amount_total) as montant_total
            FROM purchase_order
            WHERE date_order >= %s 
            AND date_order <= %s
            AND company_id = %s
            AND state IN ('purchase', 'done')
        """
        
        self.env.cr.execute(query, (date_from, date_to, date_from, date_to, company_id))
        result = self.env.cr.fetchone()
        
        if result and result[2] > 0:  # Si au moins une commande
            return [{
                'date_from': result[0],
                'date_to': result[1],
                'nb_commandes': result[2],
                'montant_total': result[3],
                'domain': [
                    ('date_order', '>=', date_from),
                    ('date_order', '<=', date_to),
                    ('company_id', '=', company_id),
                    ('state', 'in', ['purchase', 'done'])
                ],
                'model': 'purchase.order',
            }]
        return []

    def _get_pos_groupes(self, date_from, date_to):
        """Groupe les commandes POS par intervalle de date et par point de vente"""
        company_id = self.env.company.id
        
        query = """
            SELECT 
                pc.id as config_id,
                pc.name as pos_name,
                %s as date_from,
                %s as date_to,
                COUNT(po.id) as nb_commandes,
                SUM(po.amount_total) as montant_total
            FROM pos_order po
            INNER JOIN pos_session ps ON po.session_id = ps.id
            INNER JOIN pos_config pc ON ps.config_id = pc.id
            WHERE po.date_order >= %s 
            AND po.date_order <= %s
            AND po.company_id = %s
            AND po.state IN ('paid', 'done', 'invoiced')
            GROUP BY pc.id, pc.name
            ORDER BY pc.name
        """
        
        self.env.cr.execute(query, (date_from, date_to, date_from, date_to, company_id))
        results = self.env.cr.fetchall()
        
        pos_groupes = []
        for result in results:
            pos_groupes.append({
                'config_id': result[0],
                'pos_name': result[1],
                'date_from': result[2],
                'date_to': result[3],
                'nb_commandes': result[4],
                'montant_total': result[5],
                'domain': [
                    ('date_order', '>=', date_from),
                    ('date_order', '<=', date_to),
                    ('company_id', '=', company_id),
                    ('config_id', '=', result[0]),
                    ('state', 'in', ['paid', 'done', 'invoiced'])
                ],
                'model': 'pos.order',
            })
        
        return pos_groupes

    def action_view_sale_orders(self):
        """Action pour voir les commandes de vente"""
        self.ensure_one()
        domain = [
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['sale', 'done'])
        ]
        
        return {
            'name': _('Commandes de vente du %s au %s') % (self.date_from, self.date_to),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
        }

    def action_view_purchase_orders(self):
        """Action pour voir les commandes d'achat"""
        self.ensure_one()
        domain = [
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['purchase', 'done'])
        ]
        
        return {
            'name': _('Commandes d\'achat du %s au %s') % (self.date_from, self.date_to),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
        }

    def action_view_pos_orders(self, config_id=None):
        """Action pour voir les commandes POS (optionnel: filtré par config)"""
        self.ensure_one()
        domain = [
            ('date_order', '>=', self.date_from),
            ('date_order', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('state', 'in', ['paid', 'done', 'invoiced'])
        ]
        
        name = _('Commandes POS du %s au %s') % (self.date_from, self.date_to)
        
        if config_id:
            domain.append(('config_id', '=', config_id))
            config = self.env['pos.config'].browse(config_id)
            name = _('Commandes POS - %s du %s au %s') % (config.name, self.date_from, self.date_to)
        
        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
        }