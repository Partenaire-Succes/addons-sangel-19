{
    'name': 'Correction AVCO - Import Excel',
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Correction du cout moyen pondere (AVCO) via import Excel',
    'description': """
        Module de correction de l'AVCO apres migration ProgMag vers Odoo.
        - Import Excel : code article + PMP correct
        - Regle de variation 5% : prix reception conserve si ecart acceptable
        - Sauvegarde des prix originaux pour tracabilite complete
        - Multi-societe : corrections isolees par societe
    """,
    'author': 'Dev Interne',
    'depends': ['stock', 'purchase', 'account', 'custom_stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_avco_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
