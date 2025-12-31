# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class FNERefundWizard(models.TransientModel):
    _name = 'fne.refund.wizard'
    _description = "Wizard de certification FNE pour avoir"

    move_id = fields.Many2one(
        'account.move',
        string='Facture d\'avoir',
        required=True,
        readonly=True
    )
    
    original_invoice_id = fields.Many2one(
        'account.move',
        string='Facture d\'origine',
        related='move_id.reversed_entry_id',
        readonly=True,
        store=False  # Ne pas stocker pour éviter les problèmes
    )
    
    original_fne_reference = fields.Char(
        string='Référence FNE origine',
        related='original_invoice_id.fne_reference',
        readonly=True,
        store=False  # Ne pas stocker pour éviter les problèmes
    )
    
    line_ids = fields.One2many(
        'fne.refund.wizard.line',
        'wizard_id',
        string='Lignes à retourner'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Pré-remplir le wizard avec toutes les lignes de l'avoir"""
        res = super().default_get(fields_list)
        
        if self._context.get('active_id'):
            move = self.env['account.move'].browse(self._context['active_id'])
            
            if move.move_type != 'out_refund':
                raise UserError(_("Ce wizard est uniquement pour les avoirs (notes de crédit)."))
            
            if not move.reversed_entry_id:
                raise UserError(_("Aucune facture d'origine trouvée pour cet avoir."))
            
            if not move.reversed_entry_id.fne_certified:
                raise UserError(_("La facture d'origine doit être certifiée FNE."))
            
            res['move_id'] = move.id
            
            # Préparer les lignes
            lines = []
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                # Chercher la ligne correspondante dans la facture d'origine
                original_line = move.reversed_entry_id.invoice_line_ids.filtered(
                    lambda l: l.product_id == line.product_id and l.display_type == 'product'
                )
                
                # Récupérer le fne_original_line_id
                fne_id = ''
                if original_line and original_line[0].fne_original_line_id:
                    fne_id = original_line[0].fne_original_line_id
                
                lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'description': line.name,
                    'quantity': abs(line.quantity),
                    'fne_original_line_id': fne_id,
                    'move_line_id': line.id,
                    'to_refund': True if fne_id else False,  # Cocher seulement si ID FNE existe
                }))
            
            res['line_ids'] = lines
        
        return res
    
    def action_certify_fne_refund(self):
        """Certifier l'avoir via l'API FNE"""
        self.ensure_one()
        _logger.info(f"Nombre de lignes: {len(self.line_ids)}")
        
        if not self.move_id:
            raise UserError(_("Aucune facture d'avoir sélectionnée."))
        
        if self.move_id.fne_certified:
            raise UserError(_("Cet avoir est déjà certifié FNE."))
        
        # Récupérer la facture d'origine directement (pas via related)
        original_invoice = self.move_id.reversed_entry_id
        
        if not original_invoice:
            raise UserError(_("Aucune facture d'origine trouvée pour cet avoir."))
        
        if not original_invoice.fne_certified:
            raise UserError(_("La facture d'origine n'est pas certifiée FNE."))
        
        if not original_invoice.fne_invoice_uuid:
            raise UserError(_("L'identifiant UUID de la facture d'origine est manquant."))
        
        # Vérifier qu'il y a des lignes
        if not self.line_ids:
            raise UserError(_("Aucune ligne trouvée dans le wizard. Veuillez réessayer."))
        
        # Vérifier qu'il y a des lignes sélectionnées
        selected_lines = self.line_ids.filtered(lambda l: l.to_refund)
        
        if not selected_lines:
            raise UserError(_("Veuillez sélectionner au moins une ligne à retourner."))
        
        config = self.env['fne.config.settings'].get_active_config(self.move_id.company_id.id)
        if not config or not config.is_fne_enabled:
            raise UserError(_("La certification FNE n'est pas activée."))
        
        # Préparer les items
        items = []
        for line in selected_lines:
            if not line.fne_original_line_id:
                raise UserError(_(f"ID FNE manquant pour la ligne: {line.description}"))
            
            items.append({
                'id': line.fne_original_line_id,
                'quantity': line.quantity
            })
        
        if not items:
            raise UserError(_("Aucun article à retourner."))
        
        payload = {'items': items}
        
        headers = {
            'Authorization': f'Bearer {config.fne_api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        url = f"{config.fne_api_url}/external/invoices/{original_invoice.fne_invoice_uuid}/refund"
        
        try:
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            data = response.json()
            
            if response.status_code in [200, 201]:
                # Mise à jour de l'avoir
                self.move_id.write({
                    'fne_certified': True,
                    'fne_reference': data.get('reference'),
                    'fne_token': data.get('token'),
                    'fne_sticker_balance': data.get('balance_sticker'),
                    'fne_response_json': json.dumps(data, indent=2, ensure_ascii=False),
                    'fne_error_message': False
                })
                
                # Sauvegarder les IDs FNE sur les lignes de l'avoir
                for wizard_line in selected_lines:
                    if wizard_line.move_line_id:
                        wizard_line.move_line_id.write({
                            'fne_original_line_id': wizard_line.fne_original_line_id
                        })
                
                self.move_id.message_post(
                    body=f"Avoir certifié FNE avec succès. Référence: {data.get('reference')}",
                    subject="Certification FNE"
                )
                return {'type': 'ir.actions.act_window_close'}
            
            else:
                error_msg = data.get('message', 'Erreur inconnue')
                self.move_id.write({
                    'fne_error_message': json.dumps(data, indent=2, ensure_ascii=False)
                })
                raise UserError(_(f"Erreur FNE: {error_msg}\n\nDétails: {response.text}"))
        
        except requests.exceptions.RequestException as e:
            raise UserError(_(f"Erreur de connexion à l'API FNE: {str(e)}"))
        except Exception as e:
            raise UserError(_(f"Erreur lors de la certification FNE: {str(e)}"))


class FNERefundWizardLine(models.TransientModel):
    _name = 'fne.refund.wizard.line'
    _description = "Lignes du wizard avoir FNE"

    wizard_id = fields.Many2one(
        'fne.refund.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Article',
        readonly=True
    )
    
    description = fields.Char(
        string='Description',
        readonly=True
    )
    
    quantity = fields.Float(
        string='Quantité',
        readonly=True
    )
    
    fne_original_line_id = fields.Char(
        string='ID FNE origine',
        readonly=True,
        help="Identifiant de la ligne sur la plateforme FNE"
    )
    
    move_line_id = fields.Many2one(
        'account.move.line',
        string='Ligne d\'avoir',
        readonly=True
    )
    
    to_refund = fields.Boolean(
        string='Retourner',
        default=True,
        help="Cocher pour inclure cette ligne dans la certification FNE"
    )