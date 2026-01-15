{
    'name': 'Connexion SAGE X3',
    'version': '1.0',
    'category': 'stock',
    'summary': 'Connexion à la plateforme SAGE X3 pour import des produits',
    'description': 'Connexion à la plateforme FNE pour import des produits',
    'sequence': -15,
    'author': 'Partenaire de succès',
    'website': 'https://www.partenairesucces.com/',

    'depends': [
        'base',
        'account',
        'purchase',
        'sale',
        'stock',
        'custom_stock',
        'custom_partner',
        'custom_food_credit',
    ],
    'data': [
        # 'security/ir.model.access.csv',
        # 'data/import_product_from_x3_job.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/purchase_order_views.xml',
    ],

    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False
}
