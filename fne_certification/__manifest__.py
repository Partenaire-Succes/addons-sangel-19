{
    'name': 'FNE Certification',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Connexion à la plateforme FNE pour certification des factures',
    'description': 'Connexion à la plateforme FNE pour certification des factures',
    'sequence': -15,
    'author': 'Partenaire de succès',
    'website': 'https://www.partenairesucces.com/',

    'depends': [
        'base',
        'account',
        'sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        # 'views/fne_invoice_view.xml',
        'views/fne_config_settings_views.xml',
        # 'views/res_partner_views.xml',
        'views/fne_certification_wizard_views.xml',
        'views/report_invoice_fne.xml',
    ],

    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False
}
