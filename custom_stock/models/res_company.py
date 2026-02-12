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
          help="Code du site dans SAGE X3 (ex: SIEGE, ABIDJAN, etc.)"
     )
     sage_x3_journal_sale = fields.Char(
          string="Journal ventes SAGE X3",
          default="VTE",
          help="Code journal des ventes (ex: VTE)"
     )
     sage_x3_journal_cash = fields.Char(
          string="Journal caisse SAGE X3",
          default="CAISSE",
          help="Code journal caisse (ex: CAISSE)"
     )
     sage_x3_journal_bank = fields.Char(
          string="Journal banque SAGE X3",
          default="BQ",
          help="Code journal banque (ex: BQ)"
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
     
     # Comptes de trésorerie
     sage_x3_account_cash_id = fields.Many2one(
          'account.account',
          string="Compte Espèces",
          # domain="[('company_id', '=', id)]",
          help="Compte 57xxxxx pour les paiements espèces"
     )
     sage_x3_account_check_id = fields.Many2one(
          'account.account',
          string="Compte Chèque",
          # domain="[('company_id', '=', id)]",
          help="Compte 521xxxxx pour les paiements chèque"
     )
     sage_x3_account_transfer_id = fields.Many2one(
          'account.account',
          string="Compte Virement",
          # domain="[('company_id', '=', id)]",
          help="Compte 585xxxxx pour les virements"
     )
     sage_x3_account_mobile_money_id = fields.Many2one(
          'account.account',
          string="Compte Mobile Money",
          # domain="[('company_id', '=', id)]",
          help="Compte pour Mobile Money"
     )
     sage_x3_account_tpe_id = fields.Many2one(
          'account.account',
          string="Compte TPE",
          # domain="[('company_id', '=', id)]",
          help="Compte pour paiements par TPE/Carte bancaire"
     )
     
     # Envoi automatique
     sage_x3_auto_send = fields.Boolean(
          string="Envoi auto à SAGE X3",
          default=False,
          help="Envoyer automatiquement les factures validées à SAGE X3"
     )