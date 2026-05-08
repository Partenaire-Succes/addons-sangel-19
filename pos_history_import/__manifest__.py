# -*- coding: utf-8 -*-
{
    'name': 'POS - Import Historique des Ventes',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Importez vos historiques de ventes POS depuis un fichier Excel',
    'description': """
        Module d'import historique POS pour migration depuis un ancien système.
        
        Fonctionnalités :
        - Import depuis fichier Excel (.xlsx)
        - Regroupement des sessions par Jour ou par Mois
        - Création automatique de pos.session, pos.order, pos.order.line, pos.payment
        - Liaison au bon pos.config
        - Template Excel téléchargeable
        - Journal d'import détaillé avec gestion des erreurs
        - Support des commandes multi-lignes
        - Recherche de produits et clients par référence ou nom
    """,
    'author': 'Custom Dev',
    'depends': ['point_of_sale', 'custom_pos'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_import_wizard_views.xml',
        'views/pos_import_menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['openpyxl'],
    },
}
