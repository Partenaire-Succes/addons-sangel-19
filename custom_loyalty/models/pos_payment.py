# Approche simplifiée - Dans votre modèle pos.payment

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PosPayment(models.Model):
    _inherit = 'pos.payment'
    
    
    def _check_loyalty_before_payment(self):
        """
        Méthode simple appelée avant chaque paiement par carte de fidélité
        """
        if not self.payment_method_id.is_loyalty:
            return True
            
        order = self.pos_order_id
        partner = order.partner_id
        
        # Vérifications de base
        if not partner:
            raise UserError("Un client doit être sélectionné pour la carte de fidélité.")
    
        loyalty_card = self.env['loyalty.card'].search([
            ('partner_id', '=', partner.id),
        ], limit=1)
        
        if not loyalty_card:
            raise UserError("Aucune carte de fidélité valide pour ce client.")
        
        # Vérifier le solde
        solde_disponible = loyalty_card.points
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

            if payment.payment_method_id.is_loyalty:
                payment._check_loyalty_before_payment()
                payment._update_loyalty_card()
                
        return payments
            
    
    def _update_loyalty_card(self):
        """
        Met à jour la carte de fidélité utilisé
        """
        if not self.payment_method_id.is_loyalty:
            return
            
        loyalty_card = self.env['loyalty.card'].search([
            ('partner_id', '=', self.pos_order_id.partner_id.id),
        ], limit=1)
        
        if loyalty_card:
            loyalty_card.points -= self.amount
            self.env['loyalty.history'].create({
                    'card_id': loyalty_card.id,
                    'description': "POS - %s" % self.pos_order_id.pos_reference,
                    'used': self.amount,
                    'order_model': 'pos.order',
                    'order_id': self.pos_order_id.id,
                })
