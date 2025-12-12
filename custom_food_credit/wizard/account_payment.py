from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import re
import logging

_logger = logging.getLogger(__name__)

class AccountPaymentRegisterInherit(models.TransientModel):
    _inherit = 'account.payment.register'


    is_food = fields.Boolean(related='journal_id.is_food')
    is_limit = fields.Boolean(related='journal_id.is_limit')
    linked_limit = fields.Boolean('Est liee a une limite de crédit', default=False)
    linked_food = fields.Boolean('Est liee a un crédit alimentaire', default=False)
    food_solde = fields.Float('Solde: Crédit alimentaire', compute='compute_solde_food', default=0)
    limit_solde = fields.Float('Solde: Limite de crédit', compute='compute_solde_limit', default=0)
    move_id = fields.Many2one('account.move', string="Facture", related='line_ids.move_id')

    def action_create_payments(self):
        res = super(AccountPaymentRegisterInherit, self).action_create_payments()

        if self.linked_limit:
            self._process_invoice_payment()

        # if self.journal_id.is_food:
        #     self._check_credit()

        # if self.journal_id.is_limit:
        #     self._check_limit()

        return res

    def _process_invoice_payment(self):
        """Traite le paiement d'une facture"""
        limit_credit = self.env['limit.credit'].search([
            ('partner_id', '=', self.partner_id.id)
        ], limit=1)
        
        if self.amount > limit_credit.amount_limit_consumed:
            raise UserError(
                f"Le montant à régler ({self.amount:.2f} FCFA) ne peut pas "
                f"dépasser le crédit consommé actuel ({limit_credit.amount_limit_consumed:.2f} FCFA)."
            )
        new_consumed = limit_credit.amount_limit_consumed - self.amount      
        limit_credit.write({
            'amount_limit_consumed': new_consumed,
        })
        
        # Enregistrer l'opération
        self.env['limit.credit.operation'].create({
            'limit_id': limit_credit.id,
            'name': f"Règlement facture - {self.communication}",
            'amount_operation': -self.amount,
            'operation_date': fields.Datetime.now(),
        })
        
        _logger.info(
            f"Facture réglée pour {limit_credit.partner_id.name}: "
            f"{self.amount:.2f} FCFA - Nouveau crédit consommé: {new_consumed:.2f} FCFA"
        )

    @api.onchange('journal_id', 'is_food', 'move_id')
    def compute_solde_food(self):
        for record in self:
            record.food_solde = 0.0  # Valeur par défaut pour éviter l’erreur
            if record.is_food and record.move_id and record.move_id.partner_id:
                food_credit = self.env['food.credit.line'].sudo().search([
                    ('partner_id', '=', record.move_id.partner_id.id),
                    ('start', '<=', record.payment_date),
                    ('end', '>=', record.payment_date)
                ], limit=1)
                if food_credit:
                    record.food_solde = food_credit.solde
    
    @api.onchange('journal_id', 'is_limit', 'move_id')
    def compute_solde_limit(self):
        for record in self:
            record.limit_solde = 0.0
            if self.is_limit and record.move_id and record.move_id.partner_id:
                limit_credit = self.env['limit.credit'].sudo().search([
                    ('partner_id', '=', record.move_id.partner_id.id),
                ], limit=1)
                
                if limit_credit:
                    record.limit_solde = limit_credit.amount_limit_solde

    def _check_credit(self):
        for payment in self:
            if payment.is_food:
                if not payment.partner_id.is_food:
                    raise ValidationError(_("Le client %s n'a pas de crédit alimentaire attribué.") 
                                        %  payment.partner_id.name)
                
                food_credit = self.env['food.credit.line'].sudo().search([
                    ('partner_id', '=', payment.move_id.partner_id.id),
                    ('start', '<=', payment.payment_date),
                    ('end', '>=', payment.payment_date)
                ], limit=1)
                
                if not food_credit:
                    raise ValidationError(
                        _("Aucun crédit alimentaire trouvé pour le client %s dans la période spécifiée.") 
                        % payment.move_id.partner_id.name)
                
                # Calculer le solde disponible manuellement (plus fiable)
                solde_disponible = food_credit.amount - food_credit.amount_used
                _logger.info('Crédit disponible: %s', solde_disponible)
                
                if payment.amount > solde_disponible:
                    raise ValidationError(
                        _("Le montant total de la commande (%s) dépasse le crédit alimentaire disponible (%s) pour le client %s.") 
                        % (payment.amount, solde_disponible, payment.move_id.partner_id.name))
                
                # Mettre à jour amount_used
                food_credit.sudo().write({
                    'amount_used': food_credit.amount_used + payment.amount,
                    'move_ids': [(4, payment.move_id.id)]
                })
                food_credit.append_invoice_line(
                    f"GROS/(1/2 GROS): {self.payment_date} - {self.move_id.invoice_origin or self.move_id.name} - {self.amount:.2f} FCFA"
                )
                payment.linked_food = True
                self.env.invalidate_all()

    def _check_limit(self):
        for payment in self:

            if payment.is_limit:
                if not payment.partner_id.is_limit:
                    raise ValidationError(_("Le client %s n'a pas de limite crédit attribué.") 
                                        %  payment.partner_id.name)
                
                limit_credit = self.env['limit.credit'].sudo().search([
                    ('partner_id', '=', payment.move_id.partner_id.id),
                ], limit=1)
                
                if not limit_credit:
                    raise ValidationError(
                        _("Aucune limite crédit trouvé pour le client %s dans la période spécifiée.") 
                        % payment.partner_id.name)
                
                solde_disponible = limit_credit.amount_limit - limit_credit.amount_limit_consumed
                _logger.info('Crédit disponible: %s', solde_disponible)
                
                if payment.amount > solde_disponible:
                    raise ValidationError(
                        _("Le montant total de la commande (%s) dépasse la limite crédit disponible (%s) pour le client %s.") 
                        % (payment.amount, solde_disponible, payment.partner_id.name))
                
                # Mettre à jour amount_limit_consumed
                limit_credit.sudo().write({
                    'amount_limit_consumed': limit_credit.amount_limit_consumed + payment.amount,
                })
                self.env['limit.credit.operation'].create({
                    'limit_id': limit_credit.id,
                    'name': "Gros & 1/2 Gros - %s" % payment.move_id.invoice_origin or payment.move_id.name,
                    'amount_operation': payment.amount,
                    'operation_date': fields.Datetime.now(),
                })
                payment.linked_limit = True
                self.env.invalidate_all()
        
        return True
    


    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        payment_vals.update({
            'linked_limit': self.linked_limit,
            # 'linked_food': self.linked_food,
        })
        
        return payment_vals