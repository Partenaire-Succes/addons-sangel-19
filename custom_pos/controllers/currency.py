# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaires Succes.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com/>)
#    Author: Adama KONE
#
#############################################################################
"""
POS Currency Conversion Controller

Provides JSON-RPC endpoints for multi-currency payment support in POS.
Allows converting foreign currency amounts to company currency (USD).
"""

import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosCurrencyController(http.Controller):
    """Controller for POS multi-currency conversion operations."""

    @http.route('/pos/active_currencies', type='json', auth='user', csrf=False)
    def get_active_currencies(self):
        """
        Get list of active currencies with their exchange rates to company currency.
        
        Returns:
            dict: {
                'status': 'success'|'error',
                'company_currency': {id, name, symbol, position, decimal_places},
                'currencies': [{id, name, symbol, rate, inverse_rate, position, decimal_places}...],
                'message': str (if error)
            }
        
        Note:
            - Only returns active currencies (active=True)
            - Excludes company currency from the list (it's the target)
            - Rate is how much 1 unit of foreign currency equals in company currency
        """
        try:
            company = request.env.company
            company_currency = company.currency_id
            
            # Get all active currencies except company currency
            currencies = request.env['res.currency'].search([
                ('active', '=', True),
                ('id', '!=', company_currency.id)
            ], order='name')
            
            # Get current rates
            today = fields.Date.context_today(request.env.user)
            currency_data = []
            
            for currency in currencies:
                # Get conversion rate from this currency to company currency
                # rate = how much 1 unit of this currency is worth in company currency
                try:
                    rate = currency._get_conversion_rate(
                        from_currency=currency,
                        to_currency=company_currency,
                        company=company,
                        date=today
                    )
                except Exception:
                    # Fallback to inverse of stored rate
                    rate = 1.0 / (currency.rate or 1.0)
                
                currency_data.append({
                    'id': currency.id,
                    'name': currency.name,
                    'full_name': currency.currency_unit_label or currency.name,
                    'symbol': currency.symbol,
                    'rate': rate,  # 1 foreign = X company currency
                    'inverse_rate': 1.0 / rate if rate else 0,  # 1 company = X foreign
                    'position': currency.position,
                    'decimal_places': currency.decimal_places,
                    'rounding': currency.rounding,
                })
            
            return {
                'status': 'success',
                'company_currency': {
                    'id': company_currency.id,
                    'name': company_currency.name,
                    'symbol': company_currency.symbol,
                    'position': company_currency.position,
                    'decimal_places': company_currency.decimal_places,
                },
                'currencies': currency_data,
            }
            
        except Exception as e:
            _logger.exception("Error fetching active currencies for POS")
            return {
                'status': 'error',
                'message': str(e),
                'currencies': [],
            }

    @http.route('/pos/convert_currency', type='json', auth='user', csrf=False)
    def convert_currency(self, currency_id, amount):
        """
        Convert an amount from a source currency to the company currency.
        
        Args:
            currency_id (int): ID of the source currency (res.currency)
            amount (float): Amount in the source currency
            
        Returns:
            dict: {
                'status': 'success'|'error',
                'source_amount': float,
                'converted_amount': float,
                'rate_used': float,
                'source_currency': {id, name, symbol},
                'target_currency': {id, name, symbol},
                'message': str (if error)
            }
        """
        try:
            company = request.env.company
            company_currency = company.currency_id
            source_currency = request.env['res.currency'].browse(int(currency_id))
            
            if not source_currency.exists():
                return {
                    'status': 'error',
                    'message': f"Currency with ID {currency_id} not found",
                }
            
            if not source_currency.active:
                return {
                    'status': 'error',
                    'message': f"Currency {source_currency.name} is not active",
                }
            
            # Convert using Odoo's native method
            today = fields.Date.context_today(request.env.user)
            converted_amount = source_currency._convert(
                from_amount=float(amount),
                to_currency=company_currency,
                company=company,
                date=today,
                round=True
            )
            
            # Calculate rate used
            rate_used = converted_amount / float(amount) if amount else 0
            
            return {
                'status': 'success',
                'source_amount': float(amount),
                'converted_amount': converted_amount,
                'rate_used': rate_used,
                'source_currency': {
                    'id': source_currency.id,
                    'name': source_currency.name,
                    'symbol': source_currency.symbol,
                },
                'target_currency': {
                    'id': company_currency.id,
                    'name': company_currency.name,
                    'symbol': company_currency.symbol,
                },
            }
            
        except Exception as e:
            _logger.exception("Error converting currency in POS")
            return {
                'status': 'error',
                'message': str(e),
                'converted_amount': 0,
            }
