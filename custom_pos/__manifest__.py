# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaires Succes.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com/>)
#    Author: Adama KONE
#
#############################################################################
{
    'name': 'Personnalisation du Point de vente',
    'version': '18.0',
    'category': 'POS',
    'summary': """Customisation de Point de vente pour Odoo 18.0""",
    'description': """Adaptation du module Point de vente pour répondre aux besoins 
        spécifiques des utilisateurs d'Odoo 18.0.""",
    'author': 'Adams KONE',
    'company': 'Partenaires Succes',
    'maintainer': 'Adams KONE',
    'website': "https://www.partenairesucces.com/",
    'depends': ['sale','point_of_sale'],
    'data': [
        # 'security/ir.model.access.csv',
        'security/security.xml',
        'views/pos_config_inherit_views.xml',
        # 'views/product_template_inherit_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
    
    "assets": {
        "point_of_sale._assets_pos": [
            "/custom_pos/static/src/**/*",
        ],
    },
}
