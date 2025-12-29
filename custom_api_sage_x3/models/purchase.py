import requests
import logging as logger
from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError
import json
from datetime import datetime

_logger = logger.getLogger(__name__)

BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
ORDERS_URL = f"{BASE_URL}/api/Orders/batch"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

TIMEOUT = 30
MAX_RETRIES = 3


class PurchaseOrderSageX3(models.Model):
    _inherit = "purchase.order"

    # Champs pour le suivi de l'envoi vers SAGE X3
    sage_x3_order_ref = fields.Char(
        string="Référence SAGE X3",
        readonly=True,
        copy=False,
        help="Référence de la commande dans SAGE X3"
    )
    sage_x3_sent = fields.Boolean(
        string="Envoyé à SAGE X3",
        default=False,
        readonly=True,
        copy=False
    )
    sage_x3_sent_date = fields.Datetime(
        string="Date d'envoi SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_error = fields.Text(
        string="Erreur SAGE X3",
        readonly=True,
        copy=False
    )
    
    # Champs spécifiques pour SAGE X3
    sage_site_vente = fields.Char(
        string="Site de vente SAGE",
        help="Code du site de vente dans SAGE X3"
    )
    sage_magasin = fields.Char(
        string="Magasin SAGE",
        help="Code du magasin dans SAGE X3"
    )

    def button_confirm(self):
        """Surcharge de la validation pour envoyer à SAGE X3"""
        # Appel de la méthode parente (validation standard Odoo)
        res = super(PurchaseOrderSageX3, self).button_confirm()
        
        # Envoi vers SAGE X3 après validation
        for order in self:
            if not order.sage_x3_sent:
                try:
                    order.send_to_sage_x3()
                except Exception as e:
                    # Log l'erreur mais ne bloque pas la validation
                    _logger.error("❌ Erreur envoi SAGE X3 pour commande %s : %s", 
                                order.name, str(e))
                    order.write({
                        'sage_x3_error': str(e),
                    })
        
        return res

    def send_to_sage_x3(self):
        """
        Envoie la commande d'achat vers SAGE X3
        """
        self.ensure_one()
        
        if self.sage_x3_sent:
            _logger.warning("⚠️ Commande %s déjà envoyée à SAGE X3", self.name)
            return True
        
        try:
            _logger.info("📤 Envoi de la commande %s vers SAGE X3...", self.name)
            
            # 1. Authentification
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec de l'authentification SAGE X3")
            
            # 2. Préparation des données au format batch
            order_data = self._prepare_batch_order_data()
            
            # 3. Envoi vers SAGE X3
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            _logger.info("📦 Données envoyées à SAGE X3 : %s", json.dumps(order_data, indent=2))
            
            response = self._safe_post(ORDERS_URL, headers, order_data)
            
            if response.status_code in (200, 201):
                response_data = response.json()
                sage_ref = response_data.get("orderReference") or response_data.get("id") or self.name
                
                self.write({
                    'sage_x3_sent': True,
                    'sage_x3_sent_date': fields.Datetime.now(),
                    'sage_x3_order_ref': sage_ref,
                    'sage_x3_error': False,
                })
                
                _logger.info("✅ Commande %s envoyée avec succès à SAGE X3 (Ref: %s)", 
                           self.name, sage_ref)
                
                # Message dans le chatter
                self.message_post(
                    body=f"✅ Commande envoyée à SAGE X3<br/>Référence: {sage_ref}",
                    subject="Envoi SAGE X3"
                )
                
                return True
            else:
                error_msg = f"Erreur HTTP {response.status_code}: {response.text}"
                raise UserError(error_msg)
                
        except Exception as e:
            error_msg = f"Erreur lors de l'envoi à SAGE X3: {str(e)}"
            _logger.exception("❌ %s", error_msg)
            
            self.write({
                'sage_x3_error': error_msg,
            })
            
            # Message dans le chatter
            self.message_post(
                body=f"❌ Erreur envoi SAGE X3: {error_msg}",
                subject="Erreur SAGE X3"
            )
            
            raise UserError(error_msg)

    def _authenticate_sage_x3(self):
        """Authentification auprès de SAGE X3"""
        try:
            auth_data = {"username": USERNAME, "password": PASSWORD}
            response = requests.post(AUTH_URL, json=auth_data, timeout=15)
            
            if response.status_code in (200, 201):
                token = response.json().get("token")
                _logger.info("✅ Authentification SAGE X3 réussie")
                return token
            else:
                _logger.error("❌ Authentification SAGE X3 échouée: %s", response.text)
                return None
        except Exception as e:
            _logger.exception("❌ Exception authentification SAGE X3: %s", str(e))
            return None

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """Envoi POST avec retry"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ Tentative %s échouée: HTTP %s - %s", 
                              attempt, response.status_code, response.text)
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s): %s", attempt, str(e))
            
            if attempt < MAX_RETRIES:
                import time
                time.sleep(2)
        
        # Dernière tentative sans retry
        return requests.post(url, headers=headers, json=data, timeout=timeout)

    def _prepare_batch_order_data(self):
        """
        Prépare les données de la commande pour SAGE X3 au format batch
        
        Format attendu:
        {
          "commandes": [
            {
              "siteVente": "string",
              "NumeroCommande": "string",
              "DateCommande": "2025-12-23T16:10:16.741Z",
              "Client": "string",
              "Devise": "string",
              "Magasin": "string",
              "ReferenceCommandeClient": "string",
              "items": [
                {
                  "ligne": 2147483647,
                  "article": "string",
                  "TexteLigne": "string",
                  "quantite": 0.01
                }
              ]
            }
          ]
        }
        """
        self.ensure_one()
        
        # Préparation des lignes de commande
        items = []
        for idx, line in enumerate(self.order_line, start=1):
            # Vérifier que la quantité est >= 0.01 (minimum requis par l'API)
            quantity = max(line.product_qty, 0.01)
            
            item_data = {
                "ligne": idx * 1000,  # Numérotation par milliers (1000, 2000, 3000...)
                "article": line.product_id.default_code or "",
                "TexteLigne": line.name or line.product_id.name or "",
                "quantite": quantity
            }
            items.append(item_data)
        
        # Obtenir le code client (ref ou customer_id)
        client_code = self.partner_id.ref or self.partner_id.customer_id or ""
        if not client_code:
            _logger.warning("⚠️ Code client manquant pour %s, utilisation du nom", self.partner_id.name)
            client_code = self.partner_id.name[:20]  # Limitation à 20 caractères
        
        # Obtenir la devise
        currency_code = self.currency_id.name if self.currency_id else "XOF"
        
        # Obtenir le site de vente et le magasin
        site_vente = self.sage_site_vente or self.picking_type_id.warehouse_id.code or "PRINCIPAL"
        magasin = self.sage_magasin or self.picking_type_id.warehouse_id.code or "PRINCIPAL"
        
        # Construction de la commande
        commande = {
            "siteVente": site_vente,
            "NumeroCommande": self.name,
            "DateCommande": self.date_order.isoformat() if self.date_order else datetime.now().isoformat(),
            "Client": client_code,
            "Devise": currency_code,
            "Magasin": magasin,
            "ReferenceCommandeClient": self.partner_ref or self.name,
            "items": items
        }
        
        # Format batch avec tableau de commandes
        batch_data = {
            "commandes": [commande]
        }
        
        return batch_data

    def action_resend_to_sage_x3(self):
        """Action pour renvoyer manuellement à SAGE X3"""
        self.ensure_one()
        
        if self.state not in ['purchase', 'done']:
            raise UserError("La commande doit être confirmée avant l'envoi à SAGE X3")
        
        # Réinitialiser le statut d'envoi
        self.write({
            'sage_x3_sent': False,
            'sage_x3_error': False,
        })
        
        # Envoyer
        try:
            self.send_to_sage_x3()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Succès',
                    'message': 'Commande envoyée avec succès à SAGE X3',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur',
                    'message': f'Erreur lors de l\'envoi: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_view_sage_x3_status(self):
        """Affiche le statut d'envoi SAGE X3"""
        self.ensure_one()
        
        status_icon = '✅' if self.sage_x3_sent else '❌'
        error_html = f'<li><strong>Erreur:</strong> <span style="color:red;">{self.sage_x3_error}</span></li>' if self.sage_x3_error else ''
        
        message = f"""
        <h3>Statut SAGE X3</h3>
        <ul>
            <li><strong>Envoyé:</strong> {status_icon} {'Oui' if self.sage_x3_sent else 'Non'}</li>
            <li><strong>Date d'envoi:</strong> {self.sage_x3_sent_date or 'N/A'}</li>
            <li><strong>Référence SAGE X3:</strong> {self.sage_x3_order_ref or 'N/A'}</li>
            <li><strong>Site de vente:</strong> {self.sage_site_vente or 'N/A'}</li>
            <li><strong>Magasin:</strong> {self.sage_magasin or 'N/A'}</li>
            {error_html}
        </ul>
        """
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Statut SAGE X3',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"
    
    def _prepare_line_for_sage_x3(self):
        """Prépare une ligne de commande pour SAGE X3"""
        self.ensure_one()
        
        # Vérifier que la quantité est >= 0.01 (minimum requis par l'API)
        quantity = max(self.product_qty, 0.01)
        
        return {
            "ligne": self.sequence or 1000,
            "article": self.product_id.default_code or "",
            "TexteLigne": self.name or self.product_id.name or "",
            "quantite": quantity
        }