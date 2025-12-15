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
    'name': 'POS Amination Commerciale',
    'category': 'POS',
    'summary': """Customisation de Point de vente pour Odoo 18.0""",
    'description': 
        """
            Adaptation du module Point de vente, pour l'animation commerciale
        """,
    'author': 'Partenaires Succes',
    'company': 'Partenaires Succes',
    'maintainer': 'Adams KONE',
    'website': "https://www.partenairesucces.com/",
    'depends': ['sale','point_of_sale'],
    'data': [
        # 'security/ir.model.access.csv',
        'views/pos_promotion_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
    
    # "assets": {
    #     "point_of_sale._assets_pos": [
    #         "/custom_pos_amination/static/src/**/*",
    #     ],
    # },
}
