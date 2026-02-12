# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountTax(models.Model):
    _inherit = 'account.tax'

    tax_type = fields.Selection(
        [
            ('TVA', 'TVA normal de 18%'),
            ('TVAB', 'TVA réduit de 9%'),
            ('TVAC', 'TVA exec conv de 0%'),
            ('TVAD', 'TVA exec leg de 0%'),
            ('OTHER', 'Autre')
        ], 
        string='Type taxe FNE', 
        compute='_compute_tax_type', 
        store=True, readonly=False, default='TVA',
        help="Type de taxe pour la certification FNE:\n")
    @api.depends('name', 'amount')
    def _compute_tax_type(self):
        """Détermine automatiquement le type de taxe FNE"""
        for tax in self:
            if tax.amount == 18:
                tax.tax_type = 'TVA'
            elif tax.amount == 9:
                tax.tax_type = 'TVAB'
            elif tax.amount == 0 and 'CONV' in (tax.name or '').upper():
                tax.tax_type = 'TVAC'
            elif tax.amount == 0 and 'LEG' in (tax.name or '').upper():
                tax.tax_type = 'TVAD'
            else:
                tax.tax_type = 'OTHER'