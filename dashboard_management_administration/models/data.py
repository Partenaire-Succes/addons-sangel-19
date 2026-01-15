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


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    managment_admin_id = fields.Many2one('managment.admin', string='Gestion d administration')

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    managment_admin_id = fields.Many2one('managment.admin', string='Gestion d administration')

class PosOrder(models.Model):
    _inherit = 'pos.order'

    managment_admin_id = fields.Many2one('managment.admin', string='Gestion d administration')