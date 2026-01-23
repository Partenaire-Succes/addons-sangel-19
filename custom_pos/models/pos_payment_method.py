# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    is_titre_paiement = fields.Boolean(
        string="Titre de paiement",
        default=False,
        help="Si coché, ce mode de paiement apparaîtra sur le ticket de prélèvement imprimé à la fermeture de caisse."
    )
    is_cheque = fields.Boolean(
        string="Chèque",
        default=False,
        help="Si coché, ce mode de paiement est considéré comme paiement par chèque."
    )
    is_bank_card = fields.Boolean(
        string="Carte bancaire",
        default=False,
        help="Si coché, ce mode de paiement est considéré comme paiement par carte bancaire."
    )
    # Note: is_loyalty is defined in custom_loyalty module
    # Note: is_food and is_limit are defined in custom_food_credit module

    def _load_pos_data_fields(self, config_id):
        """Add custom fields to POS loaded data"""
        fields_list = super()._load_pos_data_fields(config_id)
        fields_list.extend(['is_titre_paiement', 'is_cheque', 'is_bank_card'])
        # is_loyalty loaded by custom_loyalty
        # is_food, is_limit loaded by custom_food_credit
        return fields_list
