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


class FamilyInventory(models.Model):
     _name = 'family.inventory'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Family Inventory'

     name = fields.Char(string='Libelle', required=True)
     code = fields.Char(string='Code')

class CategoryProductInherit(models.Model):
     _inherit = 'product.category'
     _rec_name = 'code'

     code = fields.Char(string='Code')

class SubFamilyInventory(models.Model):
     _name = 'sub.family.inventory'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Sub Family Inventory'

     name = fields.Char(string="Libelle", required=True)
     code = fields.Char(string='Code')
     family_id = fields.Many2one('family.inventory', string='Famille test', copy=True)
     family_categ_id = fields.Many2one('product.category', string='Famille', copy=True)