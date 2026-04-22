# -*- coding: utf-8 -*-
{
    'name': 'Personnalisation des achats',
    'version': '1.0.0',
    'summary': 'Filtrage des produits dans les commandes achat selon statut X3 et statut magasin',
    'category': 'Purchase',
    'author': 'Partenaires Succes',
    'website': 'https://www.partenairesucces.com/',
    'depends': [
        'purchase',
        'custom_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/purchase_order_inherit_views.xml',
        'wizard/supplier_price_import_wizard_views.xml',
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
