# -*- coding: utf-8 -*-
{
    'name': 'Migration Sage X3 → Odoo',
    'version': '1.0.0',
    'category': 'Tools',
    'summary': 'Module de migration des données comptables de Sage X3 vers Odoo',
    'author': 'Kone Adama',
    'depends': ['base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/x3_config_views.xml',
        'views/migration_log_views.xml',
        'views/menu_views.xml',
        'wizard/migration_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
