# -*- coding: utf-8 -*-
{
    'name': 'Afficheur Client Bixolon BCD-2000',
    'category': 'Point of Sale',
    'version': '1.0.0',
    'summary': 'Intégration afficheur VFD Bixolon BCD-2000 via Web Serial API',
    'depends': ['point_of_sale', 'custom_pos'],
    'author': 'Manzo - Marcel NZORE <nzoremarcel@gmail.com> Partenaire Succes',
    'data': [
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'custom_bixolon_display/static/src/js/bixolon_service.js',
            'custom_bixolon_display/static/src/js/bixolon_pos_patch.js',
            'custom_bixolon_display/static/src/xml/bixolon.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'AGPL-3',
}
