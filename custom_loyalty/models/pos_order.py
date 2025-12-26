# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaire Succes Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com>)
#    Author: Adama KONE
#
#############################################################################
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'
    
    rendu_monnaie = fields.Float(
        string='Rendu Monnaie',
        default=0.0,
        help="Montant du rendu monnaie à créditer sur la carte de fidélité du client"
    )
    
    def _process_saved_order(self, draft):
        """Override to process rendu_monnaie loyalty update after order is paid"""
        result = super()._process_saved_order(draft)
        
        # Only process rendu_monnaie if order is paid and has a rendu_monnaie amount
        if not draft and self.state == 'paid' and self.rendu_monnaie > 0:
            self._process_rendu_monnaie_loyalty()
        
        return result
    
    def _process_rendu_monnaie_loyalty(self):
        """Process the rendu monnaie by updating customer loyalty points"""
        self.ensure_one()
        
        if not self.partner_id:
            _logger.warning(f"POS Order {self.pos_reference}: No partner, skipping rendu monnaie")
            return
        
        if self.rendu_monnaie <= 0:
            return
        
        # Find the customer's loyalty card
        loyalty_card = self.env['loyalty.card'].search([
            ('partner_id', '=', self.partner_id.id),
        ], limit=1)
        
        if not loyalty_card:
            _logger.warning(
                f"POS Order {self.pos_reference}: Customer {self.partner_id.name} "
                f"has no loyalty card, skipping rendu monnaie of {self.rendu_monnaie}"
            )
            return
        
        # Update loyalty points
        old_points = loyalty_card.points
        loyalty_card.write({
            'points': old_points + self.rendu_monnaie,
        })
        
        # Create loyalty history entry
        self.env['loyalty.history'].create({
            'card_id': loyalty_card.id,
            'description': f"Rendu monnaie: {self.rendu_monnaie:.2f} FCFA",
            'issued': self.rendu_monnaie,
            'order_model': 'pos.order',
            'order_id': self.id,
            'pos_name': f"Caisse {self.config_id.name} - {self.pos_reference}",
        })
        
        _logger.info(
            f"POS Order {self.pos_reference}: Rendu monnaie {self.rendu_monnaie:.2f} FCFA "
            f"credited to {self.partner_id.name}'s loyalty card. "
            f"Balance: {old_points:.2f} -> {loyalty_card.points:.2f}"
        )
    

class LoyaltyHistory(models.Model):
    _inherit = 'loyalty.history'
    
    pos_name = fields.Char(
        string='Nom du POS',
    )