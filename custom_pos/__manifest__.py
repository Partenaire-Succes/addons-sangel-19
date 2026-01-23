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
    'name': 'Personnalisation du Point de vente',
    'version': '18.0',
    'category': 'POS',
    'summary': """Customisation de Point de vente pour Odoo 18.0""",
    'description': """Adaptation du module Point de vente pour répondre aux besoins 
        spécifiques des utilisateurs d'Odoo 18.0.""",
    'author': 'Adams KONE',
    'company': 'Partenaires Succes',
    'maintainer': 'Adams KONE',
    'website': "https://www.partenairesucces.com/",
    'depends': ['sale', 'point_of_sale', 'account'],
    'data': [
        # 'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_sequence_data.xml',
        'report/prelevement_ticket_report.xml',
        'report/prelevement_ticket_template.xml',
        'report/cloture_caisse_report.xml',
        'report/cloture_caisse_template.xml',
        'views/pos_config_inherit_views.xml',
        'views/pos_payment_method_inherit_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
    
    "assets": {
        "point_of_sale._assets_pos": [
            # Currency conversion feature - popup must load before patch
            "/custom_pos/static/src/js/CurrencyConversionPopup.js",
            "/custom_pos/static/src/xml/currency_conversion_popup.xml",
            "/custom_pos/static/src/js/currency_payment_screen_patch.js",
            "/custom_pos/static/src/xml/currency_payment_screen.xml",
            # Closing popup customizations
            "/custom_pos/static/src/js/closing_popup_patch.js",
            "/custom_pos/static/src/xml/closing_popup_patch.xml",
            # Money details popup customizations
            "/custom_pos/static/src/js/money_details_popup_patch.js",
            "/custom_pos/static/src/xml/money_details_popup_patch.xml",
            # Other JS files
            "/custom_pos/static/src/js/opening_control_popup_patch.js",
            "/custom_pos/static/src/js/OrderlineCustom.js",
            "/custom_pos/static/src/js/payment_screen_patch.js",
            "/custom_pos/static/src/js/ProductScreen.js",
            "/custom_pos/static/src/js/ticket_screen_refund_patch.js",
            # Other XML files
            "/custom_pos/static/src/xml/cash_move_hide_cash_in.xml",
            "/custom_pos/static/src/xml/cash_move_list_popup_patch.xml",
            "/custom_pos/static/src/xml/custom_receipt_header.xml",
            "/custom_pos/static/src/xml/opening_control_popup_patch.xml",
            "/custom_pos/static/src/xml/orderline_customization.xml",
            "/custom_pos/static/src/xml/pos_payment_screen.xml",
            "/custom_pos/static/src/xml/pos_receipt_custom.xml",
        ],
    },
}
