{
    'name': 'Personnalisation des carte de fidélité',
    'version': '1.2.0',
    'summary': 'Ce module permet de personnaliser les carte de fidélité',
    'description': 'ce module permet de personnaliser les carte de fidélité',
    'sequence': -95,
    'category': 'loyalty',
    'author': 'Partenaire de succès',
    'website': 'https://www.partenairesucces.com/',
    'depends': [
        'base',
        'product',
        'loyalty',
        'pos_loyalty',
        'point_of_sale',
        "sale_loyalty",
        "custom_stock",
        "custom_food_credit",
        "custom_partner",
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/loyalty_family_data.xml',
        'views/loyalty_family_views.xml',
        'wizard/update_loyalty_card_views.xml',
        'views/product_template_views.xml',
        'views/pos_order_inherit_views.xml',
        'views/pos_payment_method_inherit_views.xml',
        'views/res_partner_inherit_views.xml',
        # 'views/sale_order_inherit_views.xml',
    ],

    "assets": {
        "point_of_sale._assets_pos": [
            "/custom_loyalty/static/src/js/*.js",
            "/custom_loyalty/static/src/xml/*.xml",
        ],
    },

    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False
}
