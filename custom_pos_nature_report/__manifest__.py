# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaires Succes.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com/>)
#    Author: Adama KONE
#
#############################################################################
{
    'name': 'Personnalisation du Point de vente pour nature',
    'version': '19.0.1.5.0',
    'category': 'POS',
    'summary': """Customisation de Point de vente pour Odoo 19.0""",
    'description': """Adaptation du module Point de vente pour répondre aux besoins 
        spécifiques des utilisateurs d'Odoo 19.0.
        
        Modifications:
        - Prix unitaire = défini sur la Nature (une seule fois par nature)
        - Valeur monétaire = Qté nature totale × Prix unitaire
        - Prix total HT = Prix de base (list_price) × Quantité de produits vendus
        - Prix total TTC = Prix de base × (1 + taux taxe) × Quantité de produits vendus
        - Quantité de produits vendus (renommé)
    """,
    'author': 'Adams KONE',
    'company': 'Partenaires Succes',
    'maintainer': 'Adams KONE',
    'website': "https://www.partenairesucces.com/",
    'depends': ['sale', 'point_of_sale', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_nature_views.xml',
        'views/product_template_nature_views.xml',
        'views/pos_order_report_views.xml',
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
    
}
