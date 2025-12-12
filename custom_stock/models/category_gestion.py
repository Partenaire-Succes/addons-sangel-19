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


class ProductCategoryX3(models.Model):
     _name = 'product.category.x3'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Category de gestion, Niveau 6'

     name = fields.Char(string='Cat', required=True)
     stock = fields.Char(string='Site de stockage')
     description = fields.Char(string='Intitulé')


class ProductFamilyX3(models.Model):
     _name = 'product.family.x3'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Famille article X3'

     name = fields.Char(string="Code", required=True)
     description = fields.Char(string="Intitulé")
     table = fields.Integer(string="Table")


class ProductTypeX3(models.Model):
     _name = 'product.type.x3'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Type article X3'

     name = fields.Char(string="Code", required=True)
     description = fields.Char(string="Intitulé")
     table = fields.Integer(string="Table")

class ProductStatusSage(models.Model):
     _name = 'product.status.sage'
     _inherit = ['mail.thread', 'mail.activity.mixin']
     _rec_name = 'name'
     _description = 'Status article X3'

     name = fields.Char(string="Code", required=True)
     description = fields.Char(string="Intitulé")
     table = fields.Integer(string="Table")