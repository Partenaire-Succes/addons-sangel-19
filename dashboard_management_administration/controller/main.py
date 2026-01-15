# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json


class ManagmentAdminController(http.Controller):

    @http.route('/managment/admin/grouped/data', type='json', auth='user')
    def get_grouped_data(self, date_from=None, date_to=None):
        """Retourne les données groupées pour l'affichage"""
        ManagmentAdmin = request.env['managment.admin']
        data = ManagmentAdmin.get_grouped_data(date_from, date_to)
        
        # Formater les données pour l'affichage
        return {
            'success': True,
            'data': data
        }

    @http.route('/managment/admin/view/orders', type='json', auth='user')
    def view_orders(self, model, domain):
        """Action générique pour voir les commandes"""
        action = {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
        }
        
        if model == 'sale.order':
            action['name'] = 'Commandes de vente'
        elif model == 'purchase.order':
            action['name'] = 'Commandes d\'achat'
        elif model == 'pos.order':
            action['name'] = 'Commandes POS'
        
        return action