# -*- coding: utf-8 -*-
"""
POS data loaders for global discount functionality.

This module extends the POS data loading to include the fields required
for the global discount (remise globale) feature:
- Partner: discount_eligible, discount_percentage, discount_start_date, discount_end_date
- Product: discount_ligne (from product.template)
- Pricelist: allowed_company_ids (from custom_sales)
"""
from odoo import api, models


class ResPartnerPOS(models.Model):
    """Extend res.partner to load discount fields for POS."""
    _inherit = 'res.partner'

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Add global discount fields to the POS partner data."""
        fields = super()._load_pos_data_fields(config_id)
        fields.extend([
            'discount_eligible',
            'discount_percentage',
            'discount_start_date',
            'discount_end_date',
        ])
        return fields


class ProductTemplatePOS(models.Model):
    """Extend product.template to load discount_ligne field for POS."""
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Add discount_ligne field to the POS product data."""
        fields = super()._load_pos_data_fields(config_id)
        fields.append('discount_ligne')
        return fields


class ProductPricelistPOS(models.Model):
    """Extend product.pricelist to load allowed_company_ids for POS filtering."""
    _inherit = 'product.pricelist'

    @api.model
    def _load_pos_data_fields(self, config_id):
        """Add allowed_company_ids to enable pricelist company filtering in POS."""
        fields = super()._load_pos_data_fields(config_id)
        fields.append('allowed_company_ids')
        return fields
