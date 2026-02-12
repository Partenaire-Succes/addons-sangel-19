# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Champs FNE
    fne_certified = fields.Boolean(
        string="Certifiée FNE",
        default=False,
        readonly=True,
        copy=False
    )
    
    fne_id = fields.Char(
        string="ID FNE",
        readonly=True,
        copy=False,
        help="Identifiant unique de la facture sur la plateforme FNE"
    )
    
    fne_invoice_uuid = fields.Char(
        string="UUID Facture FNE",
        readonly=True,
        copy=False,
        help="UUID de la facture pour les opérations d'avoir"
    )
    
    fne_reference = fields.Char(
        string="Référence FNE",
        readonly=True,
        copy=False,
        help="Numéro de facture FNE (format: NCC + Année + Numéro)"
    )
    
    fne_token = fields.Char(
        string="Token de vérification",
        readonly=True,
        copy=False,
        help="Lien de vérification avec QR code"
    )
    
    fne_qr_code = fields.Char(
        string="QR Code FNE",
        compute='_compute_fne_qr_code',
        store=True
    )
    
    fne_sticker_balance = fields.Integer(
        string="Stickers restants",
        readonly=True,
        copy=False
    )
    
    fne_response_json = fields.Text(
        string="Réponse FNE complète",
        readonly=True,
        copy=False
    )
    
    fne_error_message = fields.Text(
        string="Message d'erreur FNE",
        readonly=True,
        copy=False
    )
    
    fne_payment_method = fields.Selection([
        ('cash', 'Espèces'),
        ('card', 'Carte bancaire'),
        ('check', 'Chèque'),
        ('mobile-money', 'Mobile Money'),
        ('transfer', 'Virement bancaire'),
        ('deferred', 'À terme')
    ], string='Méthode de paiement FNE', default='cash')
    
    fne_template = fields.Selection([
        ('B2C', 'B2C - Particulier'),
        ('B2B', 'B2B - Entreprise avec NCC'),
        ('B2G', 'B2G - Institution gouvernementale'),
        ('B2F', 'B2F - Client international')
    ], string='Type de client FNE', compute='_compute_fne_template', store=True)

    @api.depends('fne_token')
    def _compute_fne_qr_code(self):
        """Extrait le token pour générer le QR code"""
        for move in self:
            if move.fne_token:
                # Le token contient déjà l'URL complète
                move.fne_qr_code = move.fne_token
            else:
                move.fne_qr_code = False

    @api.depends('partner_id', 'partner_id.vat', 'partner_id.country_id')
    def _compute_fne_template(self):
        """Détermine automatiquement le type de client"""
        for move in self:
            if not move.partner_id:
                move.fne_template = 'B2C'
                continue
            
            partner = move.partner_id
            
            # B2F: Client international
            if partner.country_id and partner.country_id.code != 'CI':
                move.fne_template = 'B2F'
            # B2B: Entreprise avec NCC (vat commence par CI + 7 chiffres + 1 lettre)
            elif partner.vat and len(partner.vat) >= 9:
                move.fne_template = 'B2B'
            # B2G: Institution gouvernementale (à personnaliser selon vos besoins)
            elif partner.is_company and 'GOUVERNEMENT' in partner.name.upper():
                move.fne_template = 'B2G'
            # B2C: Particulier par défaut
            else:
                move.fne_template = 'B2C'

    def action_post(self):
        """Surcharge de la validation pour certification automatique"""
        res = super(AccountMove, self).action_post()
        
        # Certification automatique si configuré
        config = self.env['fne.config.settings'].get_active_config()
        if config and config.auto_certify_on_post:
            for move in self:
                if move.move_type in ['out_invoice', 'out_refund'] and not move.fne_certified:
                    try:
                        move.action_certify_fne()
                    except Exception as e:
                        _logger.warning(f"Certification FNE automatique échouée pour {move.name}: {str(e)}")
        
        return res

    def action_certify_fne(self):
        """Certifier la facture via l'API FNE"""
        self.ensure_one()
        
        if self.fne_certified:
            raise UserError(_("Cette facture est déjà certifiée FNE."))
        
        if self.state != 'posted':
            raise UserError(_("Seules les factures validées peuvent être certifiées."))
        
        if self.move_type not in ['out_invoice', 'out_refund']:
            raise UserError(_("Seules les factures de vente et avoirs peuvent être certifiés."))
        
        config = self.env['fne.config.settings'].get_active_config(self.company_id.id)
        if not config or not config.is_fne_enabled:
            raise UserError(_("La certification FNE n'est pas activée pour cette société."))
        
        # Facture d'avoir (refund)
        if self.move_type == 'out_refund':
            return self._certify_fne_refund()
        
        # Facture de vente normale
        return self._certify_fne_invoice()

    def _certify_fne_invoice(self):
        """Certifier une facture de vente"""
        config = self.env['fne.config.settings'].get_active_config(self.company_id.id)
        
        # Préparer les données
        payload = self._prepare_fne_invoice_data()
        
        # Appeler l'API
        headers = {
            'Authorization': f'Bearer {config.fne_api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.post(
                f'{config.fne_api_url}/external/invoices/sign',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            _logger.info(f"FNE Response Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                self._process_fne_success_response(data)
                
                self.message_post(
                    body=f"✅ Facture certifiée FNE: {data.get('reference')}",
                    subject="Certification FNE"
                )

                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            else:
                error_data = response.json()
                error_msg = error_data.get('message', 'Erreur inconnue')
                self.write({'fne_error_message': json.dumps(error_data, indent=2)})
                raise UserError(_(f"Erreur FNE: {error_msg}"))
                
        except requests.exceptions.RequestException as e:
            raise UserError(_(f"Impossible de se connecter à l'API FNE: {str(e)}"))

    def _certify_fne_refund(self):
        """Certifier une facture d'avoir"""
        if not self.reversed_entry_id:
            raise UserError(_("Aucune facture d'origine trouvée pour cet avoir."))
            
        original_invoice = self.reversed_entry_id
        
        if not original_invoice.fne_certified:
            raise UserError(_("La facture d'origine doit être certifiée FNE avant de créer un avoir."))
        
        if not original_invoice.fne_invoice_uuid:
            raise UserError(_("L'identifiant UUID de la facture d'origine est manquant."))
        
        config = self.env['fne.config.settings'].get_active_config(self.company_id.id)
        
        # Préparer les items pour l'avoir - on prend les lignes de l'avoir
        items = []
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            # Trouver la ligne correspondante dans la facture d'origine
            original_line = original_invoice.invoice_line_ids.filtered(
                lambda l: l.product_id == line.product_id and 
                         l.fne_original_line_id and
                         l.display_type == 'product'
            )
            
            if original_line and original_line[0].fne_original_line_id:
                items.append({
                    'id': original_line[0].fne_original_line_id,
                    'quantity': abs(line.quantity)  # Quantité positive pour l'avoir
                })
                # Sauvegarder l'ID FNE sur la ligne de l'avoir pour référence
                line.write({'fne_original_line_id': original_line[0].fne_original_line_id})
        
        if not items:
            raise UserError(_("Aucun article à retourner trouvé avec un ID FNE valide."))
        
        payload = {'items': items}
        
        headers = {
            'Authorization': f'Bearer {config.fne_api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        url = f'{config.fne_api_url}/external/invoices/{original_invoice.fne_invoice_uuid}/refund'
        
        try:
            _logger.info(f"FNE Refund Request URL: {url}")
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            _logger.info(f"FNE Refund Response Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                # Mise à jour de l'avoir avec les infos FNE
                values = {
                    'fne_certified': True,
                    'fne_reference': data.get('reference'),
                    'fne_token': data.get('token'),
                    'fne_sticker_balance': data.get('balance_sticker'),
                    'fne_response_json': json.dumps(data, indent=2, ensure_ascii=False),
                    'fne_error_message': False
                }
                self.write(values)

                self.message_post(
                    body=f"✅ Facture Avoir certifiée FNE: {data.get('reference')}",
                    subject="Certification FNE"
                )

                return {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            else:
                error_data = response.json()
                error_msg = error_data.get('message', 'Erreur inconnue')
                self.write({'fne_error_message': json.dumps(error_data, indent=2)})
                raise UserError(_(f"Erreur FNE: {error_msg}"))
                
        except requests.exceptions.RequestException as e:
            raise UserError(_(f"Impossible de se connecter à l'API FNE: {str(e)}"))

    def _prepare_fne_invoice_data(self):
        """Préparer les données pour l'API FNE"""
        self.ensure_one()
        config = self.env['fne.config.settings'].get_active_config(self.company_id.id)
        
        # Items
        items = []
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            item_data = {
                'description': line.name or line.product_id.name,
                'quantity': line.quantity,
                'amount': line.price_unit,
                'measurementUnit': line.product_uom_id.name if line.product_uom_id else 'pcs'
            }
            
            # Référence
            if line.product_id.default_code:
                item_data['reference'] = line.product_id.default_code
            
            # Remise
            if line.discount > 0:
                item_data['discount'] = line.discount

            if not self.partner_id.phone:
                raise UserError(_("Veuillez renseigner le téléphone du client pour la certification FNE."))

            if not self.partner_id.email:
                raise UserError(_("Veuillez renseigner l'email du client pour la certification FNE."))

            # Taxes
            item_taxes = []
            custom_taxes = []

            if line.tax_ids:
                for tax in line.tax_ids:
                    if tax.tax_type in ['TVA', 'TVAB', 'TVAC', 'TVAD']:
                        item_taxes.append(tax.tax_type)
                    else:
                        custom_taxes.append({
                            'name': tax.name[:20],
                            'amount': tax.amount
                        })
                
                item_data['taxes'] = item_taxes
                if custom_taxes:
                    item_data['customTaxes'] = custom_taxes
            else:
                item_data['taxes'] = ['TVAD']
            
            items.append(item_data)
        
        # Données de base
        data = {
            'invoiceType': 'sale',
            'paymentMethod': self.fne_payment_method or 'cash',
            'template': self.fne_template or 'B2C',
            'isRne': False,
            'clientCompanyName': self.partner_id.name,
            'clientPhone': self.partner_id.phone,
            'clientEmail': self.partner_id.email,
            'pointOfSale': config.fne_point_of_sale,
            'establishment': config.fne_establishment,
            'items': items
        }

        rate = self.currency_id._get_conversion_rate(
            self.currency_id,
            self.company_id.currency_id,
            self.company_id,
            self.invoice_date or fields.Date.today(),
        )
        
        # NCC pour B2B
        if self.fne_template == 'B2B' and self.partner_id.vat:
            data['clientNcc'] = self.partner_id.vat
        
        # Devise étrangère pour B2F
        if self.fne_template == 'B2F' and self.currency_id.name != 'XOF':
            data['foreignCurrency'] = self.currency_id.name
            data['foreignCurrencyRate'] = rate or 1
        else:
            data['foreignCurrency'] = ''
            data['foreignCurrencyRate'] = 0
        
        # Messages optionnels
        if config.commercial_message:
            data['commercialMessage'] = config.commercial_message
        if config.footer:
            data['footer'] = config.footer
        
        return data

    def _process_fne_success_response(self, data):
        """Traiter la réponse de succès de l'API FNE"""
        self.ensure_one()
        
        invoice_data = data.get('invoice', {})
        
        values = {
            'fne_certified': True,
            'fne_id': invoice_data.get('id'),
            'fne_invoice_uuid': invoice_data.get('id'),  # UUID pour les refunds
            'fne_reference': data.get('reference'),
            'fne_token': data.get('token'),
            'fne_sticker_balance': data.get('balance_sticker'),
            'fne_response_json': json.dumps(data, indent=2, ensure_ascii=False),
            'fne_error_message': False
        }
        
        self.write(values)
        
        # Sauvegarder les IDs FNE des lignes pour les avoirs
        for odoo_line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            for fne_item in invoice_data.get('items', []):
                # Matching plus robuste
                if (fne_item.get('description') and odoo_line.name and
                    fne_item.get('description') in odoo_line.name and 
                    abs(odoo_line.quantity - fne_item.get('quantity', 0)) < 0.01):
                    odoo_line.write({'fne_original_line_id': fne_item.get('id')})
                    break

    def action_open_fne_verification(self):
        """Ouvrir le lien de vérification FNE"""
        self.ensure_one()
        if not self.fne_token:
            raise UserError(_("Aucun lien de vérification disponible."))
        
        return {
            'type': 'ir.actions.act_url',
            'url': self.fne_token,
            'target': 'new',
        }

    def button_draft(self):
        """Empêcher le passage en brouillon des factures certifiées"""
        for move in self:
            if move.fne_certified:
                raise UserError(_("Impossible de repasser en brouillon une facture certifiée FNE."))
        return super(AccountMove, self).button_draft()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    fne_original_line_id = fields.Char(
        string="ID ligne FNE",
        readonly=True,
        copy=False,
        help="Identifiant de la ligne sur la plateforme FNE (pour les avoirs)"
    )