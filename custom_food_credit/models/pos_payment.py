# Approche simplifiée - Dans votre modèle pos.payment

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PosPayment(models.Model):
    _inherit = 'pos.payment'

    def _check_food_credit_before_payment(self):
        """
        Méthode simple appelée avant chaque paiement alimentaire
        """
        if not self.payment_method_id.is_food:
            return True
            
        order = self.pos_order_id
        partner = order.partner_id
        
        # Vérifications de base
        if not partner:
            raise UserError("Un client doit être sélectionné pour le crédit alimentaire.")
            
        if not partner.parent_id or not partner.parent_id.is_food:
            raise UserError("Ce client n'a pas accès au crédit alimentaire.")
        
        # Trouver le crédit alimentaire actif
        food_credit = self.env['food.credit.line'].search([
            ('partner_id', '=', partner.id),
            ('start', '<=', order.date_order),
            ('end', '>=', order.date_order),
            ('state', '=', 'in_progress')
        ], limit=1)
        
        if not food_credit:
            raise UserError("Aucun crédit alimentaire valide pour ce client.")
        
        # Vérifier le solde
        solde_disponible = food_credit.amount - food_credit.amount_used
        if self.amount > solde_disponible:
            raise UserError(f"Crédit insuffisant ! Disponible: {solde_disponible:.2f} FCFA")
        
        return True
    
    def _check_limit_credit_before_payment(self):
        """
        Méthode simple appelée avant chaque paiement alimentaire
        """
        if not self.payment_method_id.is_limit:
            return True
            
        order = self.pos_order_id
        partner = order.partner_id
        
        # Vérifications de base
        if not partner:
            raise UserError("Un client doit être sélectionné pour le Compte client.")
            
        if not partner.is_limit:
            raise UserError("Ce client n'a pas accès au Compte client.")
    
        limit_credit = self.env['limit.credit'].search([
            ('partner_id', '=', partner.id),
        ], limit=1)
        
        if not limit_credit:
            raise UserError("Aucune limite de crédit valide pour ce client.")
        
        # Vérifier le solde
        solde_disponible = limit_credit.amount_limit - limit_credit.amount_limit_consumed
        if self.amount > solde_disponible:
            raise UserError(f"Crédit insuffisant ! Disponible: {solde_disponible:.2f} FCFA")
        
        return True

    @api.model_create_multi
    def create(self, vals_list):
        """
        Surcharge de create pour vérifier avant création du paiement
        """
        payments = super().create(vals_list)
        
        for payment in payments:
            if payment.payment_method_id.is_food:
                payment._check_food_credit_before_payment()
                payment._update_food_credit()

            if payment.payment_method_id.is_limit:
                payment._check_limit_credit_before_payment()
                payment._update_limit_credit()
                
        return payments

    def _update_food_credit(self):
        """
        Met à jour le crédit alimentaire utilisé
        """
        if not self.payment_method_id.is_food:
            return
            
        food_credit = self.env['food.credit.line'].search([
            ('partner_id', '=', self.pos_order_id.partner_id.id),
            ('start', '<=', self.pos_order_id.date_order),
            ('end', '>=', self.pos_order_id.date_order),
            ('state', '=', 'in_progress')
        ], limit=1)
        
        if food_credit:
            food_credit.amount_used += self.amount
            food_credit.append_invoice_line(
                    f"POS: {self.payment_date} - {self.pos_order_id.pos_reference} - {self.amount:.2f} FCFA"
                )
            
    def _update_limit_credit(self):
        """
        Met à jour la limite crédit utilisé
        """
        if not self.payment_method_id.is_limit:
            return
            
        limit_credit = self.env['limit.credit'].search([
            ('partner_id', '=', self.pos_order_id.partner_id.id),
        ], limit=1)
        
        if limit_credit:
            limit_credit.amount_limit_consumed += self.amount
            self.env['limit.credit.operation'].create({
                    'limit_id': limit_credit.id,
                    'name': "POS - %s" % self.pos_order_id.pos_reference,
                    'amount_operation': self.amount,
                    'operation_date': fields.Datetime.now(),
                })
