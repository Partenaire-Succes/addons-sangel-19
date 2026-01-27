# -*- coding: utf-8 -*-
{
    'name': 'Dashboard Gestion Administration',
    'category': 'Sales',
    'summary': 'Dashboard complet pour ventes, POS et achats',
    'description': """
        Dashboard avec graphiques et tableaux pour:
        - Ventes Demi gros
        - POS Demi
        - Achats Commande
        - Top 5 clients
        - Filtres par date
    """,
    'author': 'Adama KONE',
    'company': 'Partenaires Succes',
    'maintainer': 'Adama KONE',
    'depends': [
        'base',
        'web',
        'sale_management',
        'point_of_sale',
        'purchase',
        'custom_api_sage_x3',
        'custom_stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'views/managment_admin_views.xml',
        'views/pos_actions_dashboard_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_web': [
            'dashboard_management_administration/static/lib/chart/chart.umd.min.js',
            'dashboard_management_administration/static/src/xml/dashboard.xml',
            'dashboard_management_administration/static/src/xml/pos_actions_dashboard.xml',
            'dashboard_management_administration/static/src/js/dashboard.js',
            'dashboard_management_administration/static/src/js/pos_actions_dashboard.js',
            'dashboard_management_administration/static/src/css/dashboard.css',
            'dashboard_management_administration/static/src/css/pos_actions_dashboard.scss',
        ],
    },
    'installable': True,
    'application': True,
}
