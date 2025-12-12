from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from dateutil.relativedelta import relativedelta

import logging

_logger = logging.getLogger(__name__)

class UpdateLoyaltyCardWizard(models.TransientModel):
    _name = 'update.loyalty.card.wizard'
    _description = 'Mise à jour de la carte de fidelité'
    
    loyalty_id = fields.Many2one(
        'loyalty.card', 
        string='Carte de fidélité',
        store=True,
        domain=[('partner_id', '>', 0)]
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Partenaire',
        store=True,
        readonly=True
    )
    
    points = fields.Float(
        string="Rendu monnaie", 
        default=0.0,
        help="Points à rendre de la carte de fidélité"
    )
    
    points_loyalty = fields.Float(
        string="Points Actuels", 
        related='loyalty_id.points', 
        readonly=True
    )

    order_id = fields.Many2one(
        'sale.order', 
        string='Commande',
    )
    
    pos_id = fields.Many2one(
        'pos.order', 
        string='Commande POS',
    )
    pos_name = fields.Char(
        string='Nom du POS',
        readonly=True
    )
       
    @api.constrains('points')
    def _check_points(self):
        """Validation des points"""
        for wizard in self:
            if wizard.points <= 0:
                raise ValidationError("Le nombre de points doit être supérieur à zéro.")
            
    @api.onchange('partner_id')
    def get_loyalty_card(self):
        """Met à jour la carte de fidélité en fonction du client sélectionné"""
        if self.partner_id.loyalty_card_ids:
            self.loyalty_id = self.partner_id.loyalty_card_ids[0]
        else:
            self.loyalty_id = False
    
    @api.model
    def update_loyalty_from_pos(self, partner_id, pos_order_id=False):
        """
        Méthode appelée depuis le POS pour mettre à jour les points
        
        :param partner_id: ID du partenaire
        :param points: Points à ajouter
        :param description: Description de l'opération
        :param pos_order_id: ID de la commande POS
        :return: dict avec success, new_balance et old_balance
        """
        try:
            partner = self.env['res.partner'].browse(partner_id)
            
            if not partner.exists():
                raise UserError("Partenaire introuvable.")
            
            # Récupérer ou créer la carte de fidélité
            loyalty_card = partner.loyalty_card_ids[0] if partner.loyalty_card_ids else False
            
            if not loyalty_card:
                raise UserError(
                    f"Le client {partner.name} n'a pas de carte de fidélité. "
                    "Veuillez en créer une d'abord."
                )
            
            old_points = loyalty_card.points
            points = self.points
            # Mettre à jour les points
            loyalty_card.write({
                'points': old_points + points,
            })
            
            # Créer l'historique
            history_vals = {
                'card_id': loyalty_card.id,
                'description': f"Rendu monnaie: {points:.2f} FCFA",
                'issued': points,
                'pos_name': self.pos_name or '',

            }
            
            if pos_order_id:
                history_vals.update({
                    'order_model': 'pos.order',
                    'order_id': pos_order_id,
                })
            
            self.env['loyalty.history'].create(history_vals)
            
            _logger.info(
                f"POS - Carte de fidélité mise à jour pour {partner.name}: "
                f"{old_points:.2f} + {points:.2f} = {loyalty_card.points:.2f} FCFA"
            )
            
            return {
                'success': True,
                'new_balance': loyalty_card.points,
                'old_balance': old_points,
                'partner_name': partner.name,
            }
            
        except Exception as e:
            _logger.error(f"Erreur lors de la mise à jour depuis le POS: {e}")
            raise UserError(str(e))
    
    def update_loyalty_card(self):
        """Met à jour la carte de fidélité du client sélectionné (depuis le backend)"""
        self.ensure_one()
        
        if not self.partner_id:
            raise UserError("Veuillez sélectionner un client.")
        
        if self.points <= 0:
            raise UserError("La monnaie doit être supérieure à zéro.")
        
        try:
            existing_loyalty = self.loyalty_id
            self._process_loyalty_update(existing_loyalty)
            self.env.invalidate_all()
            return {'type': 'ir.actions.act_window_close'}
            
        except Exception as e:
            _logger.error(f"Erreur lors de la mise à jour des points: {e}")
            raise UserError(f"Une erreur s'est produite: {str(e)}")
    
    def _process_loyalty_update(self, loyalty_card):
        """Traite la modification de la carte"""
        old_points = loyalty_card.points
        
        # Mettre à jour les points
        loyalty_card.write({
            'points': old_points + self.points,
        })

        operation_name = f"Rendu monnaie: {self.points:.2f} FCFA"
        pos_name = f"Caisse {self.pos_name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Déterminer le modèle et l'ID de commande
        order_model = None
        order_id = None
        
        if self.order_id:
            order_model = 'sale.order'
            order_id = self.order_id.id
        elif self.pos_id:
            order_model = 'pos.order'
            order_id = self.pos_id.id

        history_vals = {
            'card_id': loyalty_card.id,
            'description': operation_name,
            'issued': self.points,
            'pos_name': pos_name,
        }
        
        if order_model and order_id:
            history_vals.update({
                'order_model': order_model,
                'order_id': order_id,
            })
        
        self.env['loyalty.history'].create(history_vals)
        
        _logger.info(
            f"Carte de fidélité mise à jour pour {loyalty_card.partner_id.name}: "
            f"{old_points:.2f} + {self.points:.2f} = {loyalty_card.points:.2f} FCFA"
        )
    
    def action_cancel(self):
        """Ferme le wizard sans action"""
        return {'type': 'ir.actions.act_window_close'}