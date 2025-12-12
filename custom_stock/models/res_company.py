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


class ResCompany(models.Model):
     """Inherits 'res.company' and adds fields"""
     _inherit = 'res.company'
     
     dest_warehouse_id = fields.Many2one('stock.warehouse',
                         string='Affectation magasin',
                         help="Sélectionnez l'entrepôt de destination de l'entreprise.")
     lib_company = fields.Char(string='Libelle',
                         help="Nom de l'entreprise à utiliser dans le numéro d'article du produit.",
                         copy=False)
