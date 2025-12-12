{
    'name': 'Customisation du module credit Alimentaire',
    'version': '1.1.0',
    'summary': 'Module de gestion des crédits alimentaires',
    'description': '''Une entreprise cliente souscrit à un service de crédit
        alimentaire pour ses employés. Chaque mois, un montant fixe est crédité 
        sur le compte de chaque employé, utilisable uniquement dans le 
        réseau SANGEL (POS et module vente Odoo).
        ''',
    'sequence': -100,
    'category': 'Gestion',
    'author': 'Partenaire de succès',
    'website': 'https://www.partenairesucces.com/',
    'depends': [
        'base',
        'contacts',
        'stock',
        'point_of_sale',
        'account',
        'custom_stock',
        'custom_partner',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/data_food_credit.xml',
        'data/generate_credit_food.xml',
        'wizard/generate_credit_food_views.xml',
        'wizard/generate_invoice_credit_food_views.xml',
        'wizard/update_limit_credit_views.xml',
        'wizard/account_payment_register_inherit_views.xml',
        
        'views/food_credit_view.xml',
        'views/limit_credit_views.xml',
        'views/res_partner_inherit_views.xml',
        'views/pos_payment_method_inherit_views.xml',
        'views/account_payment_inherit_views.xml',
        'views/account_move_inherit_views.xml',
        'views/sale_order_inherit_views.xml',
        'views/account_tax_inherit_views.xml',
        'views/report_invoices.xml',
        
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    
    'assets': {
        'point_of_sale._assets_pos': [
            'custom_food_credit/static/src/js/paymentScreenCreditFood.js',
        ],
    },
}
