# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaires Succes.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com/>)
#    Author: Adama KONE
#
#############################################################################
{
    'name': 'Personnalisation du Module Inventaire',
    'version': '18.0',
    'category': 'Stock',
    'summary': """Customisation de Inventaire pour Odoo 18.0""",
    'description': """Adaptation du module Inventaire pour répondre aux besoins 
        spécifiques des utilisateurs d'Odoo 18.0.""",
    'author': 'Adams KONE',
    'company': 'Partenaires Succes',
    'maintainer': 'Adams KONE',
    'website': "https://www.partenairesucces.com/",
    'depends': ['base','stock','product','sale','purchase','hr','custom_pos'],
    'data': [
        'security/ir.model.access.csv',
        'security/product_security.xml',
        'data/code_category_inventory_data.xml',
        'data/data_sequence.xml',
        'data/product_pricelist_data.xml',
        'views/product_template_views.xml',
        'views/teams_inventory_views.xml',
        'views/res_company_views.xml',
        'views/code_inventory_views.xml',
        'views/physical_inventory_views.xml',
        'views/family_inventory_views.xml',
        'views/radius_inventory_views.xml',
        'views/category_gestion_x3_views.xml',
        'report/report_template_physical_inventory.xml',
        'report/report_inventaire_decompte_template.xml',
        'report/report.xml',
        'wizard/product_select_wizard_views.xml',
        'views/picking_inter_company_views.xml',
        'views/sale_order_views.xml',
        'views/stock_warehouse_orderpoint_view.xml',
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
