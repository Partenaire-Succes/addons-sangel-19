from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    linked_limit = fields.Boolean('Est liee a une limite de crédit', default=False)
    linked_food = fields.Boolean('Est liee a un crédit alimentaire', default=False)

    # def action_dratf(self):
    #     res = super(AccountPayment, self).action_draft()
    #     self._retire_credit()
    #     self._retire_limit()
    #     return res
    
    # def action_post(self):
    #     res = super(AccountPayment, self).action_post()
    #     if self.linked_food or self.linked_limit:
    #         raise ValidationError(_("Vous ne pouvez pas valider un paiement lié à un crédit alimentaire ou une limite de crédit."))
    #     return res
    
    def unlink(self):
        res = super(AccountPayment, self).unlink()
        if self.linked_food or self.linked_limit:
            raise ValidationError(_("Vous ne pouvez pas supprimer un paiement lié à un crédit alimentaire ou une limite de crédit."))
        return res

    def _retire_credit(self):
        for payment in self:
            if payment.is_food and payment.linked_food:
                food_credit = self.env['food.credit.line'].sudo().search([
                    ('partner_id', '=', payment.invoice_ids[0].partner_id.id),
                    ('start', '<=', payment.date),
                    ('end', '>=', payment.date)
                ], limit=1)
                food_credit.sudo().write({
                    'amount_used': food_credit.amount_used - payment.amount
                })
                # payment.linked_food = False
                self.env.invalidate_all()     
        return True
    

    def _retire_limit(self):
        for payment in self:
            if payment.is_limit and payment.linked_limit:
                limit_credit = self.env['limit.credit'].sudo().search([
                    ('partner_id', '=', payment.invoice_ids[0].partner_id.id),
                ], limit=1)
                limit_credit.sudo().write({
                    'amount_limit_consumed': limit_credit.amount_limit_consumed - payment.amount
                })
                self.env['limit.credit.operation'].create({
                    'limit_id': limit_credit.id,
                    'name': "Annulation Gros & 1/2 Gros - %s" % payment.invoice_ids[0].invoice_origin or payment.invoice_ids[0].name,
                    'amount_operation': - payment.amount,
                    'operation_date': fields.Datetime.now(),
                })
                # payment.linked_limit = False
                self.env.invalidate_all()     
        return True