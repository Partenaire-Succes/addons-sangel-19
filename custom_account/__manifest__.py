{
    'name': 'Personnalisation de la comptabilite',
    'summary': 'Ce module permet de personnaliser la comptabilite',
    'description': 'ce module permet de personnaliser la comptabilite',
    'sequence': -10,
    'category': 'Accounting',
    'author': 'Partenaire de succès',
    'website': 'https://www.partenairesucces.com/',
    'depends': [
        'base',
        'account',
        'account_budget',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security_rule.xml',
        'views/account_move_inherit_views.xml',
        'views/budget_analytic_daily_view.xml',
        'views/account_budget_inherit_views.xml',
        'views/account_payment_term_inherit_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False
}
