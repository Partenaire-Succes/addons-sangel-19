{
    'name': 'Correction AVCO - Import Excel',
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Correction du coût moyen pondéré (AVCO) via import Excel',
    'description': """
        Module de correction de l'AVCO après migration ProgMag vers Odoo.
        Permet d'importer un fichier Excel contenant les codes articles et PMP corrects,
        et de mettre à jour en masse les stock_move à valeur zéro.
    """,
    'author': 'Votre Société',
    'depends': ['stock', 'purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_avco_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
