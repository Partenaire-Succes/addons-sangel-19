{
    'name': 'Suivi des modifications de prix',
    'category': 'Inventory/Inventory',
    'summary': 'Suivi des modifications de prix et notifications quotidiennes',
    'description': """
        Price Change Tracker - Suivi des modifications de prix
    """,
    'author': 'Koua Alexandre',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['base', 'product', 'mail','stock','sale','custom_multi_barcode_for_products'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/product_price_history_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
        'wizard/custom_product_label_layout_views.xml',
        'report/barcode_template_report.xml',
        'wizard/product_price_history_wizard_views.xml',
        'wizard/product_price_analysis_wizard_views.xml',

        'report/price_history_report_template.xml',
        'report/product_price_analysis_templates.xml',
    ],

    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
