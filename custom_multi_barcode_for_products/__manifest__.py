# -*- coding: utf-8 -*-
{
    'name': 'Muliple code-barres du produit',
    'category': 'Warehouse',
    'summary': """Allows to create multiple barcode for a single product.""",
    'description': """This module allows to create Product multi barcode for
    Sales, Purchase, Inventory and Invoicing.""",
    'depends': ['stock', 'sale_management', 'purchase', 'account', 'point_of_sale','base','product','custom_stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/product_product_views.xml',
        'views/product_template_views.xml',
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
    ],

    # 'assets': {
    #     'point_of_sale._assets_pos': [
    #         'custom_multi_barcode_for_products/static/src/js/pos_multi_barcode.js',
    #     ],
    # },

    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
