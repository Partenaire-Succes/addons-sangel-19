# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    fne_client_type = fields.Selection(
        [
            ('B2C', 'Particulier'),
            ('B2B', 'Entreprise (NCC)'),
            ('B2G', 'Gouvernement'),
            ('B2F', 'International')
        ], 
        string='Type client FNE', 
        compute='_compute_fne_client_type', 
        store=True, readonly=False, default='B2C',
        help="Type de client pour la certification FNE:\n")
    
    @api.depends('vat', 'country_id', 'is_company')
    def _compute_fne_client_type(self):
        """Détermine automatiquement le type de client FNE"""
        for partner in self:
            if partner.country_id and partner.country_id.code != 'CI':
                partner.fne_client_type = 'B2F'
            elif partner.vat and len(partner.vat) >= 9:
                partner.fne_client_type = 'B2B'
            elif partner.is_company and 'GOUVERNEMENT' in (partner.name or '').upper():
                partner.fne_client_type = 'B2G'
            else:
                partner.fne_client_type = 'B2C'