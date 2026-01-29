import logging
import re
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'
    _rec_name = 'name'

    food_id = fields.Many2one(
        "food.credit",
        string="Crédit Alimentaire",
        copy=False,
    )
    is_food = fields.Boolean('A un credit Alimentaire', default=False)
    is_limit = fields.Boolean('A une limite de credit', default=False)
    amount_food = fields.Monetary(string="Credit Alimentaire", default=0.0)
    total_due = fields.Float(string="Test", default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    amount_credit_limit = fields.Float(string="Limite de credit", default=0.0)
    
    # Computed field for POS display - current food credit balance
    food_credit_balance = fields.Float(
        string="Solde crédit alimentaire",
        compute='_compute_food_credit_balance',
        help="Solde disponible du crédit alimentaire pour ce client"
    )
    
    @api.depends('food_id', 'parent_id', 'parent_id.is_food')
    def _compute_food_credit_balance(self):
        """Compute the current food credit balance for a partner from active food.credit.line"""
        now = datetime.now()
        FoodCreditLine = self.env['food.credit.line'].sudo()
        
        for partner in self:
            balance = 0.0
            # Check if partner has an active food credit line
            # Partners with food credit are employees of a company that has is_food=True
            if partner.parent_id and partner.parent_id.is_food:
                # Find active food credit line for this partner
                food_line = FoodCreditLine.search([
                    ('partner_id', '=', partner.id),
                    ('state', '=', 'in_progress'),
                    ('start', '<=', now),
                    ('end', '>=', now),
                ], limit=1, order='id desc')
                
                if food_line:
                    balance = food_line.solde
            
            partner.food_credit_balance = balance
    
    @api.model
    def _load_pos_data_fields(self, config):
        """Extend POS data loading to include food credit fields"""
        fields = super()._load_pos_data_fields(config)
        # Add food credit related fields
        fields.extend([
            'is_food',
            'is_limit',
            'food_credit_balance',
        ])
        return fields
    
    @api.model_create_multi
    def create(self, vals_list):
        """Surcharge de la méthode create pour gérer la création automatique de limit.credit"""
        partners = super(ResPartnerInherit, self).create(vals_list)
        
        for partner, vals in zip(partners, vals_list):
            if vals.get('is_limit'):
                self._create_credit_limit_record(partner)
                
        return partners
    
    def write(self, vals):
        """Surcharge de la méthode write pour gérer les modifications de is_limit et parent_id"""
        # Track parent_id changes BEFORE write to handle food credit line removal
        if 'parent_id' in vals and not self.env.context.get('skip_food_credit_sync'):
            for partner in self:
                old_parent = partner.parent_id
                new_parent_id = vals.get('parent_id')
                
                # If parent_id is changing (employee leaving company or moving to another)
                if old_parent and old_parent.id != new_parent_id:
                    # Remove food credit lines for this employee from the old company's credit programs
                    self._remove_food_credit_lines(partner, old_parent)
        
        # Handle archiving (active=False) - also remove from food credit
        if 'active' in vals and vals['active'] is False and not self.env.context.get('skip_food_credit_sync'):
            for partner in self:
                if partner.parent_id:
                    self._remove_food_credit_lines(partner, partner.parent_id)
        
        result = super(ResPartnerInherit, self).write(vals)
        
        if 'is_limit' in vals and not self.env.context.get('skip_credit_sync'):
            for partner in self:
                if vals['is_limit']:
                    existing_limit = self.env['limit.credit'].search([
                        ('partner_id', '=', partner.id)
                    ])
                    if not existing_limit:
                        self._create_credit_limit_record(partner)
                    else:
                        existing_limit.with_context(skip_partner_sync=True).write({
                            'is_limit': True,
                            'amount_limit': partner.amount_credit_limit
                        })
                else:
                    self._delete_credit_limit_record(partner)
        
        return result
    
    def unlink(self):
        """Override unlink to remove food credit lines when an employee is deleted"""
        for partner in self:
            if partner.parent_id and not self.env.context.get('skip_food_credit_sync'):
                self._remove_food_credit_lines(partner, partner.parent_id)
        return super(ResPartnerInherit, self).unlink()
    
    def _remove_food_credit_lines(self, partner, parent_company):
        """
        Remove food.credit.line entries for a partner when they leave a company.
        This is called when:
        - Employee's parent_id changes (leaving company)
        - Employee is archived (active=False)
        - Employee is deleted (unlink)
        
        Args:
            partner: The employee partner record
            parent_company: The company they are leaving
        """
        FoodCreditLine = self.env['food.credit.line'].sudo()
        
        # Find all food credit lines for this employee linked to the parent company
        food_lines = FoodCreditLine.search([
            ('partner_id', '=', partner.id),
            ('partner_company_id', '=', parent_company.id),
        ])
        
        if food_lines:
            # Log the removal for audit purposes
            for line in food_lines:
                _logger.info(
                    "Removing food credit line for employee '%s' (ID: %s) from company '%s' - "
                    "Food Credit: %s, Amount: %s, Used: %s",
                    partner.name, partner.id, parent_company.name,
                    line.food_id.name, line.amount, line.amount_used
                )
                
                # Post a message to the food.credit record for traceability
                if line.food_id:
                    line.food_id.message_post(
                        body=_(
                            "Employee <b>%s</b> has been removed from this food credit program. "
                            "Credit limit: %s, Amount consumed: %s, Remaining: %s",
                            partner.name,
                            line.amount,
                            line.amount_used,
                            line.solde,
                        ),
                        message_type='notification',
                    )
            
            # Delete the food credit lines
            food_lines.unlink()
            _logger.info("Successfully removed %d food credit line(s) for employee '%s'", 
                        len(food_lines), partner.name)
    
    def _create_credit_limit_record(self, partner):
        """Méthode privée pour créer un enregistrement limit.credit"""
        self.env['limit.credit'].with_context(skip_partner_sync=True).create({
            'partner_id': partner.id,
            'amount_limit': partner.amount_credit_limit,
            'is_limit': True
        })

    def _delete_credit_limit_record(self, partner):
        """Méthode privée pour supprimer l'enregistrement limit.credit lié"""
        credit_limit = self.env['limit.credit'].search([
            ('partner_id', '=', partner.id)
        ])
        if credit_limit:
            credit_limit.unlink()
    

