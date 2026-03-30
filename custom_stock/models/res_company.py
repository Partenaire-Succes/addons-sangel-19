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
     code_company = fields.Char(string='Code',
                         help="Code de l'entreprise à utiliser dans les commandes magasin.",
                         copy=False)
     
     # Paramètres SAGE X3
     sage_x3_site = fields.Char(
          string="Site SAGE X3",
          default="SIEGE",
          help="Code du site dans SAGE X3"
     )
     sage_x3_type_facli = fields.Char(
          string="Facture client SAGE X3",
          default="FACLI",
          help="Type de pièce facture client"
     )
     sage_x3_avcli = fields.Char(
          string="Avoir client SAGE X3",
          default="AVCLI",
          help="Type de pièce avoir client"
     )
     sage_x3_type_encai = fields.Char(
          string="Encaissement client SAGE X3",
          default="ENCAI",
          help="Type de pièce encaissement client"
     )
     sage_x3_type_decai = fields.Char(
          string="Decaissement client SAGE X3",
          default="DECAI",
          help="Type de pièce decaissement client"
     )
     sage_x3_journal_sale = fields.Char(
          string="Journal ventes SAGE X3",
          default="VTE",
          help="Code journal des ventes (ex: VTE)"
     )
     sage_x3_journal_caisse = fields.Char(
          string="Journal caisse SAGE Magasin",
          default="CAISSE",
          help="Code journal caisse (ex: CAISSE)"
     )
     
     # Compte de vente
     sage_x3_account_sale_id = fields.Many2one(
          'account.account',
          string="Compte de vente",
          # domain="[('account_type', '=', 'income'), ('company_id', '=', id)]",
          help="Compte 701xxxxx pour les ventes (unique par société)"
     )
     
     # Compte client par défaut (DIVERS)
     sage_x3_account_customer_default_id = fields.Many2one(
          'account.account',
          string="Compte client par défaut",
          # domain="[('account_type', '=', 'asset_receivable'), ('company_id', '=', id)]",
          help="Compte 41110000 pour les clients DIVERS"
     )
     sage_x3_account_caisse_id = fields.Many2one(
          'account.account',
          string="Compte caisse",
          help="Compte 57110005 pour les caisses des magasins"
     )
     sage_x3_account_ecart_caisse_id = fields.Many2one(
          'account.account',
          string="Compte de l'ecart de caisse",
          help="Compte 77820000 pour les ecarts de caisses des magasins"
     )
     sage_x3_account_sale_tva_18_id = fields.Many2one(
          'account.account',
          string="Compte TVA 18%",
          help="Compte 44310000 pour les ventes TVA 18%"
     )
     sage_x3_account_sale_tva_9_id = fields.Many2one(
          'account.account',
          string="Compte TVA 9%",
          help="Compte 44310000 pour les ventes TVA 9%"
     )
     
     # Envoi automatique
     sage_x3_auto_send = fields.Boolean(
          string="Envoi auto à SAGE X3",
          default=False,
          help="Envoyer automatiquement les factures validées à SAGE X3"
     )