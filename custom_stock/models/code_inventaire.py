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


class CodeInventory(models.Model):
     _name = 'code.inventory'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Code Inventory'

     name = fields.Char(string='Code', required=True)
     code_category_id = fields.Many2one('code.category.inventory', string='Categorie Code Inventaire', copy=True)


class CodeNameInventory(models.Model):
     _name = 'code.category.inventory'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Code name Inventory'

     name = fields.Char(string="Nom", required=True)