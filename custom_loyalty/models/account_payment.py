from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    linked_loyalty = fields.Boolean('Est liee a une carte de fidélité', default=False)

    def action_dratf(self):
        res = super(AccountPayment, self).action_draft()
        self._retire_loyalty_card()
        return res
    
    def action_post(self):
        res = super(AccountPayment, self).action_post()
        if self.linked_loyalty:
            raise ValidationError(_("Vous ne pouvez pas valider un paiement lié à une carte de fidélité."))
        return res
    
    def unlink(self):
        res = super(AccountPayment, self).unlink()
        if self.linked_loyalty:
            raise ValidationError(_("Vous ne pouvez pas supprimer un paiement lié à une carte de fidélité."))
        return res
    

    def _retire_loyalty_card(self):
        for payment in self:
            if payment.linked_loyalty and payment.is_loyalty:
                loyalty_card = self.env['loyalty.card'].sudo().search([
                    ('partner_id', '=', payment.invoice_ids[0].partner_id.id),
                ], limit=1)
                # loyalty_card.sudo().write({
                #     'points':  loyalty_card.points - payment.amount
                # })
                self.env['loyalty.history'].create({
                    'card_id': loyalty_card.id,
                    'description': "Annulation Gros & 1/2 Gros - %s" % payment.invoice_ids[0].invoice_origin or payment.invoice_ids[0].name,
                    'used': - payment.amount,
                    'order_model': 'account.payment',
                    'order_id': payment.id,
                })
                # payment.linked_loyalty = False
                self.env.invalidate_all()
                
                _logger.info('Points utilisé mis à jour: %s', loyalty_card.points)
            
        return True