# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class LoyaltyCardInherit(models.Model):
    """
    Override loyalty.card to preload cards for offline POS mode.
    
    By default, pos_loyalty does NOT preload any loyalty.card records 
    (_load_pos_data_domain returns False), which causes code activation 
    to fail when offline.
    
    This override preloads loyalty cards for:
    - Programs configured for this POS config
    - Gift cards and coupons with available balance
    - Loyalty cards associated with known partners
    """
    _inherit = 'loyalty.card'

    @api.model
    def _load_pos_data_domain(self, data, config):
        """
        Override to preload loyalty cards for offline code activation.
        
        We load cards that:
        1. Belong to programs configured for this POS config
        2. Have positive balance (points > 0)
        3. Are not expired OR have no expiration date
        
        This allows the POS to validate codes offline using cached data.
        """
        from odoo import fields

        # Get program IDs for this POS config
        program_ids = config._get_program_ids().ids
        
        if not program_ids:
            return False  # No programs = no cards to load
        
        # Build domain to load relevant cards:
        # - Cards belonging to POS programs
        # - With positive balance
        # - Not expired (or no expiration)
        return [
            ('program_id', 'in', program_ids),
            ('points', '>', 0),
            '|',
            ('expiration_date', '=', False),
            ('expiration_date', '>=', fields.Date.today()),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        """
        Extend loaded fields to include all data needed for offline validation.
        """
        # Get base fields from parent
        fields = super()._load_pos_data_fields(config)
        
        # Ensure we have all necessary fields for offline coupon activation
        required_fields = [
            'partner_id', 
            'code', 
            'points', 
            'program_id', 
            'expiration_date', 
            'write_date'
        ]
        
        for field in required_fields:
            if field not in fields:
                fields.append(field)
        
        return fields
