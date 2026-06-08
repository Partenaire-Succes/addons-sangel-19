# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sangel Login Page',
    'version': '19.0.0.2',
    'category': 'Inventory/Inventory',
    'sequence': 0,
    'author': 'Marcel nzoremarcel@gmail.com',
    'summary': 'Page de connexion personnalisée Sangel - Compatible Odoo 19.',
    'description': "",
    'website': 'https://www.odoo.com/app/employees',
    'images': [],
    'depends': [
        'web'
    ],
    'data': [
        "views/wms_page_login.xml",
    ],
    'demo': [

    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'assets': {
        'web.assets_frontend': [
            'crh_login_page/static/src/css/crh_style.css',
        ],
        'web.assets_backend': [],
    },
    'license': 'LGPL-3',
}
