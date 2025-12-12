{
    'name': 'Personnalisation des partenaires',
    'version': '1.1.0',
    'summary': 'Ce module permet de personnaliser les partenaires',
    'description': 'ce module permet de personnaliser les partenaires',
    'sequence': -100,
    'category': 'Contacts',
    'author': 'Partenaire de succès',
    'website': 'https://www.partenairesucces.com/',
    'depends': [
        'base',
        'contacts',
        'loyalty',
        'pos_loyalty',
        'point_of_sale',
        "sale_loyalty"
    ],
    'data': [
        'views/res_partner_inherit_views.xml',
        'views/loyalty_card_inherit_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False
}
