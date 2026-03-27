# -*- coding: utf-8 -*-
{
    'name': 'CFAO - Tableau de Bord Quotidien',
    'version': '19.0.1.0.0',
    'sequence': -16,
    'category': 'Sales/Reporting',
    'summary': 'Rapport quotidien multi-société : CA, Marge, Débits, Stock par rayon',
    'description': """
        Tableau de bord quotidien CFAO Retail
        ======================================
        - Rapport par société (multi-société)
        - Données Vente (sale.order) + Point de Vente (pos.order)
        - 4 périodes : Jour / Semaine / Mois / Année
        - Comparaison N-1 et Budget
        - Analyse par Rayon (catégorie produit) et Département
    """,
    'author': 'CFAO Retail',
    'depends': [
        'base',
        'sale',
        'point_of_sale',
        'stock',
        'account',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/cfao_dashboard_wizard_views.xml',
        'report/cfao_dashboard_report.xml',
        'report/cfao_dashboard_template.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
