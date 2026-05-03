# -*- coding: utf-8 -*-
{
    'name': 'POS - Import Extrait des Ventes',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Importez vos extraits de ventes POS depuis un fichier Excel (DATE/SESSION/COMMANDE/CODE)',
    'description': """
        Module d'import extrait POS pour migration depuis un ancien système.

        Format Excel attendu :
        DATE | SESSION | COMMANDE | CODE | QTY | PRIX UNIT HT | PRIX UNIT TTC | MARGE (ignorée)

        Fonctionnalités :
        - Import depuis fichier Excel (.xlsx)
        - Regroupement des sessions par nom de session (colonne SESSION du fichier)
        - Création automatique de pos.session, pos.order, pos.order.line, pos.payment
        - Liaison au bon pos.config
        - Template Excel téléchargeable
        - Journal d'import détaillé avec gestion des erreurs
        - Support des commandes multi-lignes
        - Recherche de produits par code (CODE) ou nom
        - Pas de gestion de clients
    """,
    'author': 'Custom Dev',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_extrait_import_wizard_views.xml',
        'views/pos_extrait_import_menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['openpyxl'],
    },
}
