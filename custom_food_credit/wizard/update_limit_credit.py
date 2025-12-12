from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from dateutil.relativedelta import relativedelta

import logging

_logger = logging.getLogger(__name__)

class UpdateLimitCreditWizard(models.TransientModel):
    _name = 'update.limit.credit.wizard'
    _description = 'Mise à jour des limites de crédits'
    
    limit_id = fields.Many2one(
        'limit.credit', 
        string='Client', 
        domain=[('amount_limit', '>', 0)]
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Partenaire',
        related='limit_id.partner_id',
        store=True,
        readonly=True
    )

    payment_id = fields.Many2one(
        'account.payment', 
        string='Paiement',
        domain="[('memo', '=', memo), ('partner_id', '=', partner_id), ('state', 'in', ['in_process', 'paid'])]"
    )
    move_id = fields.Many2one(
        'account.move', 
        string='Facture',
        domain="[('partner_id', '=', partner_id), ('state', '=', 'posted'), ('move_type', '=', 'out_invoice'), ('payment_state', 'in', ['in_payment', 'paid', 'partial'])]"
    )
    memo = fields.Char(string='Memo', related='move_id.name', readonly=True)
    amount = fields.Float(
        string="Montant", 
        default=0.0,
        help="Montant de la facture ou nouvelle limite selon le motif"
    )
    
    state = fields.Selection([
        ('invoice', 'Réglé une facture'), 
        ('limit', 'Modifier le crédit')
    ], string='Motif', default='invoice', required=True)
    
    amount_limit = fields.Float(
        string="Limite Crédit Actuelle", 
        related='limit_id.amount_limit', 
        readonly=True
    )
    
    amount_limit_consumed = fields.Float(
        string="Crédit Consommé Actuel",
        related='limit_id.amount_limit_consumed',
        readonly=True
    )
    
       
    @api.constrains('amount')
    def _check_amount(self):
        """Validation du montant"""
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError("Le montant doit être supérieur à zéro.")
            
    @api.onchange('state', 'payment_id', 'limit_id')
    def _onchange_amount(self):
        if self.state == 'invoice':
            self.amount = self.payment_id.amount if self.payment_id else 0.0
        else:
            self.amount = self.limit_id.amount_limit if self.limit_id else 0.0
    
    def update_limit_credit(self):
        """Met à jour la limite de crédit selon le motif"""
        self.ensure_one()
        
        if not self.limit_id:
            raise UserError("Veuillez sélectionner un client.")
        
        if self.amount <= 0:
            raise UserError("Le montant doit être supérieur à zéro.")
        
        try:
            existing_limit = self.limit_id
            
            if self.state == 'invoice':
                # Cas: Règlement d'une facture - diminue le crédit consommé
                self._process_invoice_payment(existing_limit)
                message = f"Facture de {self.amount:.2f} FCFA réglée avec succès"
                
            elif self.state == 'limit':
                # Cas: Modification de la limite de crédit
                self._process_limit_update(existing_limit)
                message = f"Limite de crédit modifiée de {existing_limit.amount_limit:.2f} à {self.amount:.2f} FCFA"
            else:
                raise UserError("Motif invalide sélectionné.")
            
            # Invalider le cache pour rafraîchir les données
            self.env.invalidate_all()
            return {'type': 'ir.actions.act_window_close'}
            
            # return {
            #     'type': 'ir.actions.client',
            #     'tag': 'display_notification',
            #     'params': {
            #         'title': '✅ Opération réussie',
            #         'message': message,
            #         'type': 'success',
            #         'sticky': False,
            #     },
            #     'type': 'ir.actions.act_window_close'
            # }
            
        except Exception as e:
            _logger.error(f"Erreur lors de la mise à jour du crédit: {e}")
            raise UserError(f"Une erreur s'est produite: {str(e)}")
    
    def _process_invoice_payment(self, limit_credit):
        """Traite le paiement d'une facture"""
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
            'name': f"Règlement facture - {self.invoice_id.name}",
            'amount_operation': -self.amount,
            'operation_date': fields.Datetime.now(),
        })
        
        _logger.info(
            f"Facture réglée pour {limit_credit.partner_id.name}: "
            f"{self.amount:.2f} FCFA - Nouveau crédit consommé: {new_consumed:.2f} FCFA"
        )
    
    def _process_limit_update(self, limit_credit):
        """Traite la modification de la limite de crédit"""
        old_limit = limit_credit.amount_limit
        
        # Vérifier que la nouvelle limite est supérieure au crédit déjà consommé
        if self.amount < limit_credit.amount_limit_consumed:
            raise UserError(
                f"La nouvelle limite ({self.amount:.2f} FCFA) ne peut pas être "
                f"inférieure au crédit déjà consommé ({limit_credit.amount_limit_consumed:.2f} FCFA)."
            )
        
        # Mettre à jour la limite
        limit_credit.write({
            'amount_limit': self.amount,
        })
        
        difference = self.amount - old_limit
        operation_name = (
            f"Augmentation de limite: {old_limit:.2f} → {self.amount:.2f} FCFA" 
            if difference > 0 
            else f"Réduction de limite: {old_limit:.2f} → {self.amount:.2f} FCFA"
        )
        
        self.env['limit.credit.operation'].create({
            'limit_id': limit_credit.id,
            'name': operation_name,
            'amount_operation': difference,
            'operation_date': fields.Datetime.now(),
        })
        
        _logger.info(
            f"Limite de crédit modifiée pour {limit_credit.partner_id.name}: "
            f"{old_limit:.2f} → {self.amount:.2f} FCFA"
        )
    
    def action_cancel(self):
        """Ferme le wizard sans action"""
        return {'type': 'ir.actions.act_window_close'}