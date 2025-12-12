from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import re
import logging

_logger = logging.getLogger(__name__)

class AccountPaymentRegisterInherit(models.TransientModel):
    _inherit = 'account.payment.register'


    is_loyalty = fields.Boolean(related='journal_id.is_loyalty')
    linked_loyalty = fields.Boolean('Est liee a une carte de fidélité', default=False)
    loyalty_solde = fields.Float('Solde: Carte de fidélité', compute='compute_solde_loyalty', default=0)
    

    def action_create_payments(self):
        res = super(AccountPaymentRegisterInherit, self).action_create_payments()

        if self.journal_id.is_loyalty:
            self._check_loyalty()

        return res

    

    @api.onchange('journal_id', 'is_loyalty', 'move_id')
    def compute_solde_loyalty(self):
        for record in self:
            record.loyalty_solde = 0.0  # Valeur par défaut pour éviter l’erreur
            if record.is_loyalty and record.move_id and record.move_id.partner_id:
                loyalty_card = self.env['loyalty.card'].sudo().search([
                    ('partner_id', '=', record.move_id.partner_id.id),
                ], limit=1)
                if loyalty_card:
                    record.loyalty_solde = loyalty_card.points


    def _check_loyalty(self):
        for payment in self:

            if payment.is_loyalty:
                if not payment.partner_id.is_loyalty:
                    raise ValidationError(_("Le client %s n'a pas de carte de fidelité attribué.") 
                                        %  payment.partner_id.name)

                loyalty_card = self.env['loyalty.card'].sudo().search([
                    ('partner_id', '=', payment.move_id.partner_id.id),
                ], limit=1)
                
                if not loyalty_card:
                    raise ValidationError(
                        _("Aucune carte de fidelité valide trouvée pour le client %s") 
                        % payment.partner_id.name)
                
                solde_disponible = loyalty_card.points
                _logger.info('points disponible: %s', solde_disponible)
                
                if payment.amount > solde_disponible:
                    raise ValidationError(
                        _("Le montant total de la commande (%s) dépasse les points de la carte de fidelité disponible (%s) pour le client %s.") 
                        % (payment.amount, solde_disponible, payment.partner_id.name))
                
                # Mettre à jour points
                loyalty_card.sudo().write({
                    'points': solde_disponible - payment.amount,
                })

                self.env['loyalty.history'].create({
                    'card_id': loyalty_card.id,
                    'description': "Gros & 1/2 Gros - %s" % payment.move_id.invoice_origin or payment.move_id.name,
                    'used': payment.amount,
                    'order_model': 'account.payment.register',
                    'order_id': payment.id,
                })
                payment.linked_loyalty = True
                self.env.invalidate_all()
        
        return True
    


    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        payment_vals.update({
            'linked_loyalty': self.linked_loyalty,
        })
        
        return payment_vals