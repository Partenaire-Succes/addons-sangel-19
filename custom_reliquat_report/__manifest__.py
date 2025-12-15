{
    'name': 'Rapports de Reliquats',
    'sequence': -100,
    'category': 'Inventory/Inventory',
    'summary': 'Gestion des rapports de reliquats avec taux de satisfaction',
    'description': """
        Module pour la gestion des rapports de reliquats avec :
        - Édition et impression des rapports de reliquats
        - Rapports mensuels et hebdomadaires
        - Calcul du taux de satisfaction basé sur les quantités commandées/reçues
        - Traçabilité complète
    """,
    'author': 'Partenaire de succes',
    'website': 'https://www.partenairesucces.com/',
    'depends': ['base', 'stock', 'purchase', 'sale', 'mail', 'point_of_sale','project'],
    'data': [
        'security/ir.model.access.csv',
        'views/reliquat_report_views.xml',
        'views/purchase_order_views.xml',
        'views/pos_asset_index_inherit.xml',
        'views/stock_backorder_confirmation_views.xml',
        'reports/reliquat_report_template.xml',
        'wizard/reliquat_report_wizard_views.xml',
        # 'data/ir_cron_data.xml',
    ],

    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
