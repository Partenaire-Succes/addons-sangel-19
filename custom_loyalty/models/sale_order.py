import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'


    payment_mode = fields.Selection(
        selection_add=[('loyalty', 'Carte de fidélité')],
        ondelete={'loyalty': 'set default'},
    )
    is_loyalty = fields.Boolean('Carte de fidélité')

    def action_confirm(self):
        res = super(SaleOrderInherit, self).action_confirm()
        self._check_loyalty_card()
        return res
    

    def _program_check_compute_points(self, programs):
        """
        Override pour calculer les points selon family_loyalty
        """
        result = super()._program_check_compute_points(programs)
        
        for program in programs.filtered(lambda p: p.program_type == 'loyalty'):
            if program in result and 'error' not in result[program]:
                custom_points = self._calculate_custom_loyalty_points_sale(program)
                
                if custom_points is not None and custom_points >= 0:
                    result[program]['points'] = [custom_points]
        
        return result
    
    def _calculate_custom_loyalty_points_sale(self, program):
        """
        Calcule les points personnalisés basés sur family_loyalty_id (Many2one dynamique)
        """
        self.ensure_one()
        
        # Group totals by loyalty family ID for dynamic calculation
        totals_by_family = {}
        
        # Récupérer les produits valides pour le programme
        products_per_rule = program._get_valid_products(self.order_line.product_id)
        valid_products = set()
        for rule, products in products_per_rule.items():
            valid_products.update(products.ids)
        
        for line in self.order_line:
            # Ignorer les lignes de récompense, combo items, quantité <= 0
            if line.product_uom_qty <= 0:
                continue
            
            product = line.product_id
            
            # Vérifier is_eligible
            if not product.is_eligible:
                continue
            
            # Vérifier family_loyalty_id (Many2one)
            family = product.family_loyalty_id
            if not family:
                continue
            
            # Vérifier si le produit est valide pour le programme
            if product.id not in valid_products:
                continue
            
            # Montant de la ligne
            line_total = self._get_order_line_price(line, 'price_total')
            
            # Accumuler par famille ID
            family_id = family.id
            if family_id not in totals_by_family:
                totals_by_family[family_id] = {
                    'total': 0.0,
                    'family': family,
                }
            totals_by_family[family_id]['total'] += line_total
        
        # Calculer les points totaux en utilisant les valeurs dynamiques de chaque famille
        total_points = 0
        for family_id, data in totals_by_family.items():
            family = data['family']
            if family.price_threshold > 0:
                # Dynamic calculation: floor(total / price_threshold) * points_earned
                points = int(data['total'] / family.price_threshold) * family.points_earned
                total_points += points
                _logger.info(
                    'Famille "%s": %.2f FCFA -> %d points (%d pts / %.0f F)',
                    family.name, data['total'], points, 
                    family.points_earned, family.price_threshold
                )
        
        _logger.info('TOTAL POINTS SALE ORDER: %d', total_points)
        return total_points
    
    def _check_loyalty_card(self):
        for order in self:
            if order.payment_mode == 'loyalty':
                if not order.partner_id.is_loyalty:
                    raise ValidationError(_("Le client %s n'a pas de carte de fidelité attribué.") 
                                        %  order.partner_id.name)
                
                loyalty_card = self.env['loyalty.card'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                ], limit=1)
                
                if not loyalty_card:
                    raise ValidationError(
                        _("Aucune carte de fidelité trouvé pour le client %s dans la période spécifiée.") 
                        % order.partner_id.name)
                
                solde_disponible = loyalty_card.points
                _logger.info('Points disponible: %s', solde_disponible)
                
                if order.amount_total > solde_disponible:
                    raise ValidationError(
                        _("Le montant total de la commande (%s) dépasse les points de la carte de fidelité disponible (%s) pour le client %s.") 
                        % (order.amount_total, solde_disponible, order.partner_id.name))
                
                # Mettre à jour points
                loyalty_card.sudo().write({
                    'points': solde_disponible - order.amount_total,
                })
                self.env['loyalty.history'].create({
                    'card_id': loyalty_card.id,
                    'description': "Gros & 1/2 Gros - %s" % order.name,
                    'used': order.amount_total,
                    'order_model': 'sale.order',
                    'order_id': order.id,
                })
                order.is_loyalty = True
                
                # Invalider tout le cache
                self.env.invalidate_all()

        return True

    def _action_cancel(self):
        """Override to restore loyalty points when order is cancelled."""
        # Restore loyalty points before cancellation
        self._retire_loyalty_card()
        return super()._action_cancel()

    def _retire_loyalty_card(self):
        """Restore loyalty card points when order is cancelled."""
        for order in self:
            if order.payment_mode == 'loyalty' and order.is_loyalty:
                loyalty_card = self.env['loyalty.card'].sudo().search([
                    ('partner_id', '=', order.partner_id.id),
                ], limit=1)
                if loyalty_card:
                    loyalty_card.sudo().write({
                        'points': loyalty_card.points + order.amount_total
                    })
                    self.env['loyalty.history'].create({
                        'card_id': loyalty_card.id,
                        'description': "Annulation Gros & 1/2 Gros - %s" % order.name,
                        'used': -order.amount_total,
                        'order_model': 'sale.order',
                        'order_id': order.id,
                    })
                    order.is_loyalty = False
                    self.env.invalidate_all()
                    
                    _logger.info('Points utilisé mis à jour: %s', loyalty_card.points)

        return True