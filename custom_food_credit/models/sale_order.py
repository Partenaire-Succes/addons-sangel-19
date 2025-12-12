from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'

    mode_payment = fields.Selection([
            ('credit', 'Credit'), 
            ('cash', 'Cash'),
        ], string='Clients à compte', default='cash')
    is_airsi_eligible = fields.Boolean(related="partner_id.is_airsi_eligible")
    payment_mode = fields.Selection([
            ('carte', 'Compte client '), 
            ('food', 'Credit alimentaire'),
            ('other', 'Autre')
        ], string='Mode de payment', default='other', required=True)
    
    is_food = fields.Boolean('Credit Alimentaire')
    is_limit = fields.Boolean('Limite Credit')

    @api.onchange('mode_payment')
    def _onchange_mode_payment(self):
        """Recalculer les lignes quand le mode de paiement change"""
        for line in self.order_line:
            line._compute_amount()

    
    def action_confirm(self):
        res = super(SaleOrderInherit, self).action_confirm()
        self._check_credit_food()
        self._check_credit_limit()
        return res
    

    def _check_credit_food(self):
        for order in self:
            if order.payment_mode == 'food':
                if not order.partner_id.parent_id.is_food:
                    raise ValidationError(_("Le client %s n'a pas de crédit alimentaire attribué.") 
                                        %  order.partner_id.name)

                food_credit = self.env['food.credit.line'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                    ('state', '=', 'in_progress'),
                    ('start', '<=', order.date_order),
                    ('end', '>=', order.date_order)
                ], limit=1)
                _logger.info('Crédit alimentaire trouvé: %s', food_credit.read())

                if not food_credit:
                    raise ValidationError(
                        _("Aucun crédit alimentaire en cours trouvé pour le client %s dans la période spécifiée.") 
                        % order.partner_id.name)

                # Calculer le solde disponible manuellement (plus fiable)
                solde_disponible = food_credit.amount - food_credit.amount_used
                _logger.info('Crédit disponible: %s', solde_disponible)

                if order.amount_total > solde_disponible:
                    raise ValidationError(
                        _("Le montant total de la commande (%s) dépasse le crédit alimentaire disponible (%s) pour le client %s.") 
                        % (order.amount_total, solde_disponible, order.partner_id.name))

                # Mettre à jour amount_used
                food_credit.sudo().write({
                    'amount_used': food_credit.amount_used + order.amount_total,
                })
                food_credit.append_invoice_line(
                    f"GROS/(1/2 GROS): {self.date_order} - {self.name} - {self.amount_total:.2f} FCFA"
                )
                order.is_food = True

                # Invalider tout le cache pour être sûr
                self.env.invalidate_all()

                _logger.info('Crédit utilisé mis à jour: %s', food_credit.amount_used)
        return True
    
    
    def _check_credit_limit(self):
        for order in self:
            if order.payment_mode == 'carte':
                if not order.partner_id.is_limit:
                    raise ValidationError(_("Le client %s n'a pas de limite crédit attribué.") 
                                        %  order.partner_id.name)

                limit_credit = self.env['limit.credit'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                ], limit=1)

                if not limit_credit:
                    raise ValidationError(
                        _("Aucune limite crédit trouvé pour le client %s dans la période spécifiée.") 
                        % order.partner_id.name)

                solde_disponible = limit_credit.amount_limit - limit_credit.amount_limit_consumed
                _logger.info('Crédit disponible: %s', solde_disponible)

                if order.amount_total > solde_disponible:
                    raise ValidationError(
                        _("Le montant total de la commande (%s) dépasse la limite crédit disponible (%s) pour le client %s.") 
                        % (order.amount_total, solde_disponible, order.partner_id.name))

                # Mettre à jour amount_limit_consumed
                limit_credit.sudo().write({
                    'amount_limit_consumed': limit_credit.amount_limit_consumed + order.amount_total,
                })
                self.env['limit.credit.operation'].create({
                    'limit_id': limit_credit.id,
                    'name': "Gros & 1/2 Gros - %s" % order.name,
                    'amount_operation': order.amount_total,
                    'operation_date': fields.Datetime.now(),
                })
                order.is_limit = True

                # Invalider tout le cache
                self.env.invalidate_all()
        return True
    

class SaleOrderLineInherit(models.Model):
    _inherit = 'sale.order.line'
    
    @api.depends('product_id', 'order_id.mode_payment', 'order_id.is_airsi_eligible')
    def _compute_tax_id(self):
        """Calculer les taxes en ajoutant AIRSI si nécessaire"""
        super()._compute_tax_id()
        
        for line in self:
            if not line.product_id:
                continue
            
            base_taxes = line.tax_id
            
            # Vérifier si on doit ajouter la taxe AIRSI
            should_apply_airsi = (
                line.order_id.is_airsi_eligible and 
                line.order_id.mode_payment == 'credit' and
                line.product_id.airsi_tax_id
            )
            
            if should_apply_airsi:
                # Ajouter la taxe AIRSI si elle n'est pas déjà présente
                airsi_tax = line.product_id.airsi_tax_id
                if airsi_tax and airsi_tax not in base_taxes:
                    line.tax_id = base_taxes | airsi_tax
            else:
                # Retirer la taxe AIRSI si elle est présente mais ne devrait pas l'être
                line.tax_id = base_taxes.filtered(lambda t: not t.is_airsi)


class SaleOrderCancelMixin(models.Model):
    """Mixin to handle food/limit credit restoration on order cancellation.
    
    In Odoo 19, sale.order.cancel wizard was removed. 
    Cancellation is now handled via _action_cancel on sale.order.
    """
    _inherit = 'sale.order'

    def _action_cancel(self):
        """Override to restore food/limit credits when order is cancelled."""
        # Restore credits before cancellation
        self._retire_credit_food()
        self._retire_credit_limit()
        return super()._action_cancel()

    def _retire_credit_food(self):
        """Restore food credit when order is cancelled."""
        for order in self:
            if order.payment_mode == 'food' and order.is_food:
                food_credit = self.env['food.credit.line'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                    ('start', '<=', order.date_order),
                    ('end', '>=', order.date_order)
                ], limit=1)
                if food_credit:
                    _logger.info('Crédit alimentaire trouvé: %s', food_credit.read())
                    food_credit.sudo().write({
                        'amount_used': food_credit.amount_used - order.amount_total
                    })
                    order.is_food = False
                    self.env.invalidate_all()
                    _logger.info('Crédit utilisé mis à jour: %s', food_credit.amount_used)
        return True

    def _retire_credit_limit(self):
        """Restore limit credit when order is cancelled."""
        for order in self:
            if order.payment_mode == 'carte' and order.is_limit:
                limit_credit = self.env['limit.credit'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                ], limit=1)
                if limit_credit:
                    limit_credit.sudo().write({
                        'amount_limit_consumed': limit_credit.amount_limit_consumed - order.amount_total
                    })
                    self.env['limit.credit.operation'].create({
                        'limit_id': limit_credit.id,
                        'name': "Annulation Gros & 1/2 Gros - %s" % order.name,
                        'amount_operation': -order.amount_total,
                        'operation_date': fields.Datetime.now(),
                    })
                    order.is_limit = False
                    self.env.invalidate_all()
                    _logger.info('Crédit utilisé mis à jour: %s', limit_credit.amount_limit_consumed)
        return True