from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)
ENDPOINT_URL = "http://54.247.95.108/ws/external/invoices/sign"
class FneCertificationWizard(models.TransientModel):
    _name = 'fne.certification.wizard'
    _description = 'Certification FNE DGI'
    
    move_id = fields.Many2one(
        'account.move', 
        string='Facture',
        store=True,
        readonly=True
    )

    fne_config_id = fields.Many2one(
        'fne.config.settings',
        string='Configuration FNE',
        store=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Client',
        store=True,
        readonly=True
    )
    
    payment_mode = fields.Selection([
        ('cash', 'Espèces'), 
        ('card', 'Carte Bancaire'), 
        ('mobile-money', 'Mobile Money'), 
        ('check', 'Chèque'),
        ('transfer', 'Virement Bancaire'),
        ('deferred', 'à terme'),
        ],
        string='Mode de Paiement',
        default='cash',
        required=True
    )
    
    invoice_type = fields.Selection([
        ('sale', 'Vente'), 
        ('purchase', 'Bordereau d’achats'),
        ],
        string='Type de Facture',
        default='sale',
        compute='default_get_move_type',
        required=True
    )

    template_type = fields.Selection([
        ('B2B', 'B2B'), 
        ('B2C', 'B2C'),
        ('B2F', 'B2F'),
        ('B2G', 'B2G'),
        ],
        string='Type de facturation',
        default='B2C',
        required=True
    )

    company_id = fields.Many2one(
        'res.company', 
        string='Société',
        store=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    
    currency_id = fields.Many2one(
        'res.currency', 
        string='Devise',
        store=True,
        readonly=True,
        default=lambda self: self.env.company.currency_id,
    )

    taxe_type = fields.Selection([
        ('TVA', 'TVA normal de 18%'), 
        ('TVAB', 'TVA réduit de 9%'),
        ('TVAC', 'TVA exec conv de 0%'),
        ('TVAD', 'TVA exec leg de 0% pour TEE et RME'),
        ],
        string='Type de Taxe',
        default='TVA',
        required=True
    )

    @api.onchange('move_id')
    def default_get_move_type(self):
        if self.move_id:
            if self.move_id.move_type in ['out_invoice', 'out_refund']:
                self.invoice_type = 'sale'
            elif self.move_id.move_type in ['in_invoice', 'in_refund']:
                self.invoice_type = 'purchase'

    def verify_partner_info(self):
        
        if not self.partner_id:
            raise UserError("Le client est requis pour la certification FNE.")

        if self.template_type != 'B2B':
            return True

        partner = self.partner_id
        if partner.company_type == 'company' and not partner.vat:
            raise UserError("Le numéro de TVA est requis pour les clients B2B.")

        if partner.company_type == 'person' and partner.parent_id and not partner.parent_id.vat:
            raise UserError("Le numéro de TVA est requis pour les clients B2B.")

        return True
    

    def prepare_payload(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError("Aucune facture sélectionnée pour la certification FNE.")
        
        invoice = self.move_id
        if invoice.fne_certified:
            raise UserError("Cette facture est déjà certifiée FNE.")
        
        fne_config = self.fne_config_id or self.env['fne.config.settings'].search([], limit=1)
        if not fne_config:
            raise UserError("La configuration FNE est manquante. Veuillez la configurer avant de continuer.")
        # if fne_config.state != 'validated':
        #     raise UserError("La configuration FNE n'est pas validée. Veuillez la valider avant de continuer.")
        
        fne_point_of_sale = fne_config.fne_point_of_sale
        establishment = fne_config.fne_establishment

        line_items = []
        for line in invoice.invoice_line_ids:
            line_items.append({
                "reference": line.product_id.default_code or "",
                "description": line.name,
                "quantity": line.quantity,
                "amount": line.price_unit,
                "discount": line.discount,
                "measurementUnit": line.product_uom_id.name or "unit",
                "taxes": [self.taxe_type],
            })
        
        payload = {
            "paymentMethod": self.payment_mode,
            "invoiceType": self.invoice_type,
            "template": self.template_type,
            "clientNcc": invoice.partner_id.parent_id.vat if invoice.partner_id.company_type == 'person' and invoice.partner_id.parent_id else invoice.partner_id.vat or "",
            "clientCompanyName": invoice.partner_id.parent_id.name if invoice.partner_id.company_type == 'person' and invoice.partner_id.parent_id else invoice.partner_id.name or "",
            "clientPhone": invoice.partner_id.phone or "",
            "clientEmail": invoice.partner_id.email or "",
            "pointOfSale": fne_point_of_sale,
            "establishment": establishment,
            "items": line_items,
            "foreignCurrency": self.currency_id.name if self.currency_id else 'XOF',
            
        }
        
        return payload
    

    # def action_certify_fne(self):
    #     for invoice in self:
    #         self.verify_partner_info()
    #         payload = self.prepare_payload()
    #         fne_config = self.env['fne.config.settings'].search([], limit=1)
    #         fne_api_token = fne_config.fne_api_token
    #         headers = {
    #             "Content-Type": "application/json",
    #             "Authorization": "Bearer " + fne_api_token
    #         }

    #         try:
    #             response = requests.post("http://54.247.95.108/ws/external/invoices/sign", headers=headers, data=json.dumps(payload))

    #             if response.status_code == 200 or response.status_code == 201:
    #                 data = response.json()
    #                 invoice.move_id.fne_certified = True
    #                 invoice.move_id.fne_reference = data.get("reference")
    #                 invoice.move_id.fne_token = data.get("token")
    #                 invoice.move_id.fne_sticker_balance = data.get("balance_funds")
    #                 invoice.move_id.fne_response_json = json.dumps(data, indent=2)
    #                 # ✅ Notification visuelle
    #                 return {
    #                     'type': 'ir.actions.client',
    #                     'tag': 'display_notification',
    #                     'params': {
    #                         'title': 'Facture certifiée',
    #                         'message': f"Référence FNE : {invoice.move_id.fne_reference}",
    #                         'type': 'success',
    #                         'sticky': False,
    #                     }
    #                 }
    #             else:
    #                 raise UserError(f"Erreur FNE : {response.text}")

    #         except requests.exceptions.RequestException as e:
    #             raise UserError(f"Erreur de connexion à FNE : {str(e)}")
            
    def action_certify_fne(self):
        for wizard in self:
            invoice = wizard.move_id
            if not invoice:
                raise UserError("Aucune facture sélectionnée.")
            if invoice.fne_certified:
                raise UserError("Cette facture est déjà certifiée FNE.")

            # Vérification de la configuration FNE
            fne_config = wizard.fne_config_id or self.env['fne.config.settings'].search([], limit=1)
            if not fne_config:
                raise UserError("La configuration FNE est manquante. Veuillez la configurer avant de continuer.")
            # Construction du payload
            payload = wizard.prepare_payload()
            fne_api_token = fne_config.fne_api_token
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {fne_api_token}"
            }

            try:
                response = requests.post(
                    ENDPOINT_URL,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=10
                )
                if response.status_code in [200, 201]:
                    data = response.json()

                    # Mise à jour de la facture
                    invoice.fne_certified = True
                    invoice.fne_reference = data.get("reference")
                    invoice.fne_token = data.get("token")
                    invoice.id_fne = data.get("invoice", {}).get("id")
                    invoice.fne_sticker_balance = data.get("balance_sticker")
                    invoice.fne_response_json = json.dumps(data, indent=2)

                    # Mise à jour des lignes avec ID FNE
                    fne_items = data.get("invoice", {}).get("items", [])
                    for item in fne_items:
                        for line in invoice.invoice_line_ids:
                            if line.name == item.get("description") and not line.fne_original_line_id:
                                line.fne_original_line_id = item.get("id")

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Facture certifiée FNE',
                            'message': f"Référence : {invoice.fne_reference}",
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                elif response.status_code == 401:
                    raise UserError("Clé API invalide (401 Unauthorized).")

                elif response.status_code == 400:
                    raise UserError(f"Point de vente ou établissement invalides (400 Bad Request)")
                else:
                    raise UserError(f"Erreur FNE : {response.text}")

            except requests.exceptions.RequestException as e:
                raise UserError(f"Erreur réseau vers FNE : {str(e)}")
            
    def action_cancel(self):
        """Ferme le wizard sans action"""
        return {'type': 'ir.actions.act_window_close'}