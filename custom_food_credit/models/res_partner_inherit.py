from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


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
    
    @api.model_create_multi
    def create(self, vals_list):
        """Surcharge de la méthode create pour gérer la création automatique de limit.credit"""
        partners = super(ResPartnerInherit, self).create(vals_list)
        
        for partner, vals in zip(partners, vals_list):
            if vals.get('is_limit'):
                self._create_credit_limit_record(partner)
                
        return partners
    
    def write(self, vals):
        """Surcharge de la méthode write pour gérer les modifications de is_limit"""
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
    

