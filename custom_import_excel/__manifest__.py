# -*- coding: utf-8 -*-
{
    'name': 'Import Excel - Données',
    'version': '1.0.0',
    'summary': 'Centralisation de tous les wizards d\'import Excel du projet Sangel',
    'description': '''
        Regroupe tous les imports Excel de données :
        - Points fidélité (loyalty.card)
        - Codes-barres produits (product.multiple.barcodes)
        - Prix fournisseurs (product.supplierinfo)
        - Stock & contacts (stock.warehouse.orderpoint / res.partner)
        - Règles de réassort Min/Max (stock.warehouse.orderpoint)
        - Correction prix PMP inventaire (physical.inventory.line)
        - Limite crédit consommée (limit.credit)
    ''',
    'category': 'Stock',
    'author': 'Adama KONE',
    'company': 'Partenaires Succes',
    'maintainer': 'Adama KONE',
    'website': 'https://www.partenairesucces.com/',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'stock',
        'stock_account',
        'product',
        'sale',
        'purchase',
        'account',
        'point_of_sale',
        'pos_loyalty',
        'custom_stock',
        'custom_pos',
        'custom_purchase',
        'custom_multi_barcode_for_products',
        'custom_food_credit',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/import_excel_dashboard_views.xml',
        'wizard/import_loyalty_points_wizard_views.xml',
        'wizard/import_barcodes_wizard_views.xml',
        'wizard/supplier_price_import_wizard_views.xml',
        'wizard/stock_excel_import_wizard_views.xml',
        'wizard/orderpoint_import_wizard_views.xml',
        'wizard/fix_price_inventory_wizard_views.xml',
        'wizard/import_limit_credit_wizard_views.xml',
        'wizard/pos_import_wizard_views.xml',
        'wizard/stock_avco_wizard_views.xml',
        'wizard/sale_margin_recompute_wizard_views.xml',
        'wizard/product_status_import_wizard_views.xml',
        'wizard/physical_inventory_line_cleanup_wizard_views.xml',
        'wizard/physical_inventory_line_excel_delete_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
