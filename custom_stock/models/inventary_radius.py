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


class RadiusInventory(models.Model):
     _name = 'radius.inventory'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Radius Inventory'

     name = fields.Char(string='Libelle', required=True)
     code = fields.Char(string='Code')


class SubRadiusInventory(models.Model):
     _name = 'sub.radius.inventory'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Sub Radius Inventory'

     name = fields.Char(string="Libelle", required=True)
     code = fields.Char(string='Code')
     radius_id = fields.Many2one('radius.inventory', string='Rayon', copy=True)