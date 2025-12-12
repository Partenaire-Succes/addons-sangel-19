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


class FoodCredit(models.Model):
    _name = 'food.credit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'credit Alimentaire'

    name = fields.Char(string='Nom', readonly=True, copy=False)
    partner_company_id = fields.Many2one('res.partner', 
                                         string='Entreprise cliente', 
                                         required=True)
    start = fields.Datetime(string="Date de debut", default=fields.Datetime.now, required=True, copy=False)
    end = fields.Datetime(string='Date de fin', copy=False)
    amount = fields.Float(string='Montant du credit', required=True)
    total_amount_limit = fields.Float(string="Limite Credit total du partenaire", compute='compute_total_amount_limit')
    count_child = fields.Integer(string="Nombre d'employees", compute='_compute_count_child')
    amount_used = fields.Float('Montants consommés', compute='compute_amount_used', store=True)
    invoiced = fields.Boolean(string='Facturé', default=False)
    move_id = fields.Many2one('account.move', string='Facture associée', readonly=True)
    responsible_id = fields.Many2one('res.users', string='Responsable', default=lambda self: self.env.user, required=True)
    state = fields.Selection([
            ('draft', 'Brouillon'), 
            ('in_progress', 'En cours'), 
            ('done', 'Terminé')
        ], string='État', default='draft', required=True)
    note = fields.Text('Note')
    partner_ids = fields.One2many(
        'res.partner', 
        'food_id',
        compute='get_partner_company',
        string='Bénéficiaires', 
        copy=True)
    line_ids = fields.One2many(
        'food.credit.line', 
        'food_id',
        string='Lignes de crédit', 
        copy=True)
    company_id = fields.Many2one('res.company', string='Société', required=True, default=lambda self: self.env.company, readonly=True)


    @api.onchange('partner_company_id')
    def get_partner_company(self):
        domain = [('parent_id', '=', self.partner_company_id.id)]
        partners = self.env['res.partner'].search(domain)
        self.partner_ids = [(6, 0, partners.ids)]

    @api.depends('line_ids.amount_used')
    def compute_amount_used(self):
        for record in self:
            record.amount_used = sum(line.amount_used for line in record.line_ids)

    def _compute_count_child(self):
        for record in self:
            record.count_child = self.env['res.partner'].search_count([('parent_id', '=', record.partner_company_id.id)])


    @api.onchange('amount', 'lines.amount')
    def compute_total_amount_limit(self):
        for record in self:
            record.total_amount_limit = sum(line.amount for line in record.line_ids)


    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_("Vous ne pouvez supprimer que les credits alimentaires à l'état Brouillon."))
        return super(FoodCredit, self).unlink()
    
    def action_done(self):
        if not self.line_ids:
            raise UserError(_("Vous devez d'abord créer les lignes des clients."))
        self.write({'state': 'in_progress'})

    def action_close(self):
        self.write({'state': 'done'})


    def action_generate_credits_with_lines(self):
        """Action unifiée pour créer les crédits et générer toutes les lignes"""
        today = datetime.now()
        start_date = today.replace(day=1)
        end_date = (start_date + relativedelta(months=1)) - relativedelta(days=1)
        
        months_fr = {
            1: 'JANVIER', 2: 'FÉVRIER', 3: 'MARS', 4: 'AVRIL',
            5: 'MAI', 6: 'JUIN', 7: 'JUILLET', 8: 'AOÛT',
            9: 'SEPTEMBRE', 10: 'OCTOBRE', 11: 'NOVEMBRE', 12: 'DÉCEMBRE'
        }
        
        month_name = months_fr[today.month]
        year = today.year
        
        # Rechercher toutes les sociétés avec un montant de crédit alimentaire
        companies = self.env['res.partner'].search([
            ('is_company', '=', True),
            ('amount_food', '>', 0),
            ('is_food', '=', True)
        ])
        
        created_credits = []
        existing_credits = []
        total_lines_created = 0
        
        for company in companies:
            name = f"CREDIT/{month_name}/{year}/{company.name.upper()}"
            
            # Vérifier si le crédit existe déjà
            existing_credit = self.env['food.credit'].search([
                ('name', '=', name)
            ], limit=1)
            
            if existing_credit:
                existing_credits.append(existing_credit)
                continue
            
            # Créer le crédit
            food_credit = self.env['food.credit'].create({
                'name': name,
                'partner_company_id': company.id,
                'amount': company.amount_food,
                'start': start_date.date(),
                'end': end_date.date(),
            })
            
            # Générer les lignes pour ce crédit
            lines_count = self._create_lines_for_credit(food_credit)
            total_lines_created += lines_count
            
            created_credits.append(food_credit)
        
        # Préparer le message de retour
        message_parts = []
        if created_credits:
            message_parts.append(f"{len(created_credits)} crédit(s) créé(s)")
        if existing_credits:
            message_parts.append(f"{len(existing_credits)} crédit(s) existaient déjà")
        if total_lines_created:
            message_parts.append(f"{total_lines_created} ligne(s) générée(s)")
        
        message = " - ".join(message_parts)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Génération des crédits terminée',
                'message': message,
                'type': 'success' if created_credits else 'info',
            }
        }
    
    def _create_lines_for_credit(self, food_credit):
        """Créer les lignes pour un crédit spécifique"""
        # Supprimer les lignes existantes (au cas où)
        food_credit.line_ids.unlink()
        
        # Rechercher les partenaires enfants de la société
        partners = self.env['res.partner'].search([
            ('parent_id', '=', food_credit.partner_company_id.id),
            ('active', '=', True)  # Seulement les partenaires actifs
        ])
        
        lines_created = 0
        for partner in partners:
            self.env['food.credit.line'].create({
                'partner_id': partner.id,
                'amount': food_credit.partner_company_id.amount_food,
                'start': food_credit.start,
                'end': food_credit.end,
                'food_id': food_credit.id,
                'partner_company_id': food_credit.partner_company_id.id,
            })
            lines_created += 1
        
        return lines_created

    def action_regenerate_selected_credits(self):
        """Régénérer les lignes pour les crédits sélectionnés"""
        total_lines = 0
        for record in self:
            # Supprimer les anciennes lignes
            record.line_ids.unlink()
            # Créer les nouvelles lignes
            lines_count = self._create_lines_for_credit(record)
            total_lines += lines_count
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Régénération terminée',
                'message': f'Lignes régénérées pour {len(self)} crédit(s) - {total_lines} ligne(s) créée(s)',
                'type': 'success',
            }
        }


class FoodCreditLine(models.Model):
    _name = 'food.credit.line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'food credit line'

    partner_id = fields.Many2one(
        'res.partner',
        'Client'
    ) 
    partner_name = fields.Char(related='partner_id.name', string='Nom du client', store=True)
    amount = fields.Float('Montant du crédit mensuel', default=0)
    start = fields.Datetime(string="Date de debut", default=fields.Datetime.now, required=True, copy=False)
    end = fields.Datetime(string='Date de fin', copy=False, required=True)
    food_id = fields.Many2one(
        'food.credit',
        'Crédit alimentaire'
    )
    solde = fields.Float('Solde disponible', default=0, compute='compute_solde')
    amount_used = fields.Float('Montants consommés')
    partner_company_id = fields.Many2one('res.partner', 
                                         string='Entreprise cliente', 
                                         required=True)
    state = fields.Selection(related='food_id.state', string='État', store=True)
    invoice_text = fields.Text('Factures')
    move_ids = fields.Many2many('account.move', string='Facture associée', readonly=True)


    def append_invoice_line(self, text):
        if text:
            self.invoice_text = (self.invoice_text or "") + f"{text}\n"


    @api.onchange('amount', 'amount_used')
    def compute_solde(self):
        for record in self:
            record.solde = record.amount - record.amount_used