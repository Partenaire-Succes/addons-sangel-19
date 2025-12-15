{
    'name': 'Personnalisation des ventes',
    'version': '1.0.0',
    'sequence': -100,
    'summary': 'Ce module permet de personnaliser les ventes, les listes de prix et les devis',
    'description': 'Ce module permet de personnaliser les ventes, les listes de prix et les devis',
    'category': 'Sales',
    'author': 'Succès de partenaire',
    'website': 'https://www.partenairesucces.com/',
    'depends': [
        'base',
        'sale',
        'product',
        'custom_stock',
    ],

    'data': [
        'security/ir.model.access.csv',
        'data/product_pricelist_rule_data.xml',
        'data/product_template_rule_data.xml',
        'wizard/product_pricelist_item_views.xml',
        # 'wizard/sale_order_payment_wizard_views.xml',

        'views/product_pricelist_inherit_views.xml',
        'views/product_template_inherit_views.xml',
        'views/product_product_inherit_views.xml',
        'views/sale_customer_invoice_views.xml',
        # 'views/sale_order_views.xml',



    ],

    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False
}
