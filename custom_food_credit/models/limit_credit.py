# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaire Succes Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com>)
#    Author: Adama KONE
#
#############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime
from dateutil.relativedelta import relativedelta

import logging

_logger = logging.getLogger(__name__)


class LimitCredit(models.Model):
    _name = 'limit.credit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Limite des credits'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', 
                                         string='Client', 
                                         required=True)
    is_limit = fields.Boolean(string="Limite Credit",
                                              related='partner_id.is_limit',
                                              readonly=True)
    amount_limit = fields.Float(string="Limite Credit par employe", related='partner_id.amount_credit_limit', readonly=False)
    amount_limit_consumed = fields.Float(string="Limite Credit Consommée", default=0.0)
    amount_limit_solde = fields.Float(string="Solde disponible", compute='compute_amount_limit_solde')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    operations_ids = fields.One2many(
        'limit.credit.operation', 
        'limit_id',
        string='Operation limite de credit', 
        copy=True)

    _sql_constraints = [
        ('unique_partner_credit_limit', 
         'UNIQUE(partner_id)', 
         'Un partenaire ne peut avoir qu\'une seule limite de crédit!')
    ]
    
    @api.model_create_multi
    def create(self, vals):
        """Synchroniser le champ is_limit avec res.partner"""
        record = super(LimitCredit, self).create(vals)
        
        if record.partner_id and record.is_limit and not self.env.context.get('skip_partner_sync'):
            record.partner_id.with_context(skip_credit_sync=True).write({
                'is_limit': True
            })
            
        return record
    
    def write(self, vals):
        """Synchroniser les modifications avec res.partner"""
        result = super(LimitCredit, self).write(vals)
        
        if 'is_limit' in vals and not self.env.context.get('skip_partner_sync'):
            for record in self:
                if record.partner_id:
                    record.partner_id.with_context(skip_credit_sync=True).write({
                        'is_limit': vals['is_limit']
                    })
        
        return result
    
    @api.onchange('amount_limit','amount_limit_consumed')
    def compute_amount_limit_solde(self):
        for record in self:
            record.amount_limit_solde = record.amount_limit - record.amount_limit_consumed


    def open_limit_credit_form(self):
        """Ouvre la vue forme de la limite de credit sélectionné"""
        return {
            'name': _('Limite de credit: {}').format(self.partner_id.name),
            'type': 'ir.actions.act_window',
            'res_model': 'limit.credit',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'create': False,
                'edit': True,
                'form_view_initial_mode': 'edit'
            }
        }


class LimitCreditOperation(models.Model):
    _name = 'limit.credit.operation'

    name = fields.Char(string='Nom', required=True, copy=False)
    amount_operation = fields.Float(string="Montant", default=0.0)
    operation_date = fields.Datetime("Date de l'operation")
    limit_id = fields.Many2one('limit.credit', string='Limite de credit')