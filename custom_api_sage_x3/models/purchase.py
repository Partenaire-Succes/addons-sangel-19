import requests
import logging as logger
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import json
from datetime import datetime
import time

_logger = logger.getLogger(__name__)

BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
ORDERS_SEND_URL = f"{BASE_URL}/api/Orders/batch"
ORDERS_RECEIVE_URL = f"{BASE_URL}/api/Orders/deliveries"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

TIMEOUT = 30
MAX_RETRIES = 3


class PurchaseOrderSageX3(models.Model):
    _inherit = "purchase.order"

    # Champs pour le suivi SAGE X3
    sage_x3_submitted = fields.Boolean(
        string="Soumis à SAGE X3",
        default=False,
        readonly=True,
        copy=False,
        help="Indique si la commande a été soumise à SAGE X3 pour validation"
    )
    sage_x3_validated = fields.Boolean(
        string="Validé par SAGE X3",
        default=False,
        readonly=True,
        copy=False,
        help="Indique si SAGE X3 a validé la commande"
    )
    sage_x3_submitted_date = fields.Datetime(
        string="Date soumission SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_order_id = fields.Integer(
        string="ID SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_response_message = fields.Text(
        string="Message SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_error = fields.Text(
        string="Erreur SAGE X3",
        readonly=True,
        copy=False
    )

    # CHAMPS ET MÉTHODES DE SOUMISSION À SAGE X3
    sage_x3_delivery_received = fields.Boolean(
        string="Livraison reçue de SAGE X3",
        default=False,
        readonly=True,
        help="Indique qu'une confirmation de livraison a été reçue de SAGE X3"
    )
    sage_x3_delivery_date = fields.Datetime(
        string="Date livraison SAGE X3",
        readonly=True
    )

    def button_confirm(self):
        """
        Surcharge de la validation : 
        Ne peut confirmer que si validé par SAGE X3
        """
        for order in self:
            if not order.sage_x3_validated:
                raise UserError(
                    "❌ Cette commande doit d'abord être soumise et validée par SAGE X3.\n\n"
                    "Utilisez le bouton 'Soumettre à SAGE X3' pour envoyer la commande."
                )
        
        # Si validé par SAGE X3, continuer le processus normal
        return super(PurchaseOrderSageX3, self).button_confirm()

    def action_submit_to_sage_x3(self):
        """
        Bouton : Soumettre la commande à SAGE X3 pour validation
        """
        self.ensure_one()
        
        if self.state not in ['draft', 'sent']:
            raise UserError("Seules les commandes en brouillon ou envoyées peuvent être soumises à SAGE X3")
        
        if self.sage_x3_submitted and self.sage_x3_validated:
            raise UserError("Cette commande a déjà été validée par SAGE X3")
        
        try:
            self.submit_to_sage_x3()
            
            if self.sage_x3_validated:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Succès',
                        'message': f'Commande validée par SAGE X3.\n{self.sage_x3_response_message or ""}',
                        'type': 'success',
                        'sticky': False,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '⚠️ Attention',
                        'message': f'Commande soumise mais non validée.\n{self.sage_x3_error or ""}',
                        'type': 'warning',
                        'sticky': True,
                    }
                }
                
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '❌ Erreur',
                    'message': f'Erreur lors de la soumission: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def submit_to_sage_x3(self):
        """
        Soumet la commande à SAGE X3 pour validation
        """
        self.ensure_one()

        order_data = self._prepare_order_for_sage_x3()
        _logger.info("📦 Données envoyées à SAGE X3 :\n%s", json.dumps(order_data, indent=2))
        
        
        # try:
        #     _logger.info("📤 Soumission de la commande %s à SAGE X3...", self.name)
            
        #     # 1. Authentification
        #     token = self._authenticate_sage_x3()
        #     if not token:
        #         raise UserError("Échec de l'authentification SAGE X3")
            
        #     # 2. Préparation des données
        #     order_data = self._prepare_order_for_sage_x3()
            
        #     # 3. Envoi vers SAGE X3
        #     headers = {
        #         "Authorization": f"Bearer {token}",
        #         "Content-Type": "application/json",
        #         "Accept": "application/json"
        #     }
            
        #     _logger.info("📦 Données envoyées à SAGE X3 :\n%s", json.dumps(order_data, indent=2))
            
        #     response = self._safe_post(ORDERS_SEND_URL, headers, order_data)
            
        #     if response.status_code in (200, 201):
        #         response_data = response.json()
                
        #         # Traiter la réponse
        #         if isinstance(response_data, list) and len(response_data) > 0:
        #             result = response_data[0]
                    
        #             success = result.get("success", False)
        #             message = result.get("message", "")
        #             commande = result.get("commande", {})
        #             sage_id = commande.get("id")
                    
        #             if success:
        #                 # Commande validée par SAGE X3
        #                 self.write({
        #                     'sage_x3_submitted': True,
        #                     'sage_x3_validated': True,
        #                     'sage_x3_submitted_date': fields.Datetime.now(),
        #                     'sage_x3_order_id': sage_id,
        #                     'sage_x3_response_message': message,
        #                     'sage_x3_error': False,
        #                 })
                        
        #                 _logger.info("✅ Commande %s validée par SAGE X3 (ID: %s)", self.name, sage_id)
                        
        #                 self.message_post(
        #                     body=f"""
        #                     <h3>✅ Commande validée par SAGE X3</h3>
        #                     <ul>
        #                         <li><strong>ID SAGE X3:</strong> {sage_id}</li>
        #                         <li><strong>Message:</strong> {message}</li>
        #                         <li><strong>Date:</strong> {fields.Datetime.now()}</li>
        #                     </ul>
        #                     <p>Vous pouvez maintenant confirmer la commande.</p>
        #                     """,
        #                     subject="✅ Validation SAGE X3"
        #                 )
                        
        #                 return True
        #             else:
        #                 # Commande rejetée par SAGE X3
        #                 self.write({
        #                     'sage_x3_submitted': True,
        #                     'sage_x3_validated': False,
        #                     'sage_x3_submitted_date': fields.Datetime.now(),
        #                     'sage_x3_error': message,
        #                 })
                        
        #                 _logger.warning("⚠️ Commande %s rejetée par SAGE X3: %s", self.name, message)
                        
        #                 self.message_post(
        #                     body=f"""
        #                     <h3>❌ Commande rejetée par SAGE X3</h3>
        #                     <p><strong>Raison:</strong> {message}</p>
        #                     <p>Veuillez corriger les erreurs et soumettre à nouveau.</p>
        #                     """,
        #                     subject="❌ Rejet SAGE X3"
        #                 )
                        
        #                 raise UserError(f"SAGE X3 a rejeté la commande:\n{message}")
        #         else:
        #             raise UserError("Format de réponse SAGE X3 invalide")
        #     else:
        #         error_msg = f"Erreur HTTP {response.status_code}: {response.text}"
        #         raise UserError(error_msg)
                
        # except Exception as e:
        #     error_msg = f"Erreur lors de la soumission à SAGE X3: {str(e)}"
        #     _logger.exception("❌ %s", error_msg)
            
        #     self.write({
        #         'sage_x3_submitted': True,
        #         'sage_x3_validated': False,
        #         'sage_x3_error': error_msg,
        #         'sage_x3_submitted_date': fields.Datetime.now(),
        #     })
            
        #     self.message_post(
        #         body=f"""
        #         <h3>❌ Erreur soumission SAGE X3</h3>
        #         <p>{error_msg}</p>
        #         """,
        #         subject="❌ Erreur SAGE X3"
        #     )
            
        #     raise

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
                time.sleep(2)
        
        return requests.post(url, headers=headers, json=data, timeout=timeout)

    def _prepare_order_for_sage_x3(self):
        """
        Prépare les données de la commande pour SAGE X3
        """
        self.ensure_one()
        
        # Validation des données requises
        if not self.partner_id:
            raise UserError("Le fournisseur est obligatoire")
        
        if not self.order_line:
            raise UserError("La commande doit contenir au moins une ligne")
        
        # Préparation des lignes
        items = []
        for idx, line in enumerate(self.order_line, start=1):
            if not line.product_id.default_code:
                raise UserError(f"Le produit '{line.product_id.name}' n'a pas de référence interne (default_code)")
            
            quantity = max(line.product_qty, 1)
            
            item_data = {
                "ligne": idx * 1000,  # Numérotation: 1000, 2000, 3000...
                "article": line.product_id.default_code,
                "TexteLigne": line.name or line.product_id.name or "",
                "quantite": quantity
            }
            items.append(item_data)
        
        # Code client (fournisseur)
        client_code = self.partner_id.ref or self.partner_id.customer_id or ""
        if not client_code:
            _logger.warning("⚠️ Code fournisseur manquant pour %s", self.partner_id.name)
            # Utiliser l'ID du partenaire comme fallback
            client_code = f"ODO{self.partner_id.id}"
        
        # Devise (champ natif)
        currency_code = self.currency_id.name if self.currency_id else "XOF"
        
        # Construction de la commande avec mapping des champs natifs
        commande = {
            "siteVente": "VRIDI",  # Fixe comme demandé
            "NumeroCommande": self.name,  # Champ natif: name
            "DateCommande": self.date_order.isoformat() if self.date_order else datetime.now().isoformat(),
            "Devise": currency_code,  # Champ natif: currency_id.name
            "Client": self.company_id.name if self.company_id else "PRINCIPAL",  # Champ natif: company_id.name
            "items": items
        }
        
        return {"commandes": [commande]}

    def action_reset_sage_x3_validation(self):
        """Réinitialise le statut SAGE X3 (pour tests ou corrections)"""
        self.ensure_one()
        
        if self.state not in ['draft', 'sent']:
            raise UserError("Seules les commandes en brouillon peuvent être réinitialisées")
        
        self.write({
            'sage_x3_submitted': False,
            'sage_x3_validated': False,
            'sage_x3_error': False,
            'sage_x3_response_message': False,
        })
        
        self.message_post(
            body="🔄 Statut SAGE X3 réinitialisé",
            subject="Réinitialisation SAGE X3"
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succès',
                'message': 'Statut SAGE X3 réinitialisé',
                'type': 'info',
            }
        }


    # ============================================================================
    # PARTIE 2 : RÉCUPÉRATION DES LIVRAISONS DEPUIS SAGE X3
    # ============================================================================


    def _safe_get(self, url, headers, params=None, timeout=TIMEOUT):
        """Appel GET avec retry"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ Tentative %s échouée: HTTP %s", attempt, response.status_code)
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s): %s", attempt, str(e))
            
            if attempt < MAX_RETRIES:
                time.sleep(2)
        
        return requests.get(url, headers=headers, params=params, timeout=timeout)

    @api.model
    def import_deliveries_from_sage_x3(self):
        """
        Récupère les livraisons depuis SAGE X3
        À appeler via un cron ou manuellement
        """
        try:
            _logger.info("🔄 Récupération des livraisons depuis SAGE X3...")
            
            # 1. Authentification
            auth_data = {"username": USERNAME, "password": PASSWORD}
            response = requests.post(AUTH_URL, json=auth_data, timeout=15)
            
            if response.status_code not in (200, 201):
                raise UserError("Échec de l'authentification SAGE X3")
            
            token = response.json().get("token")
            
            # 2. Récupération des livraisons
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
            
            response = self._safe_get(ORDERS_RECEIVE_URL, headers)
            
            if response.status_code == 200:
                deliveries = response.json()
                
                if not deliveries:
                    _logger.info("ℹ️ Aucune livraison à récupérer")
                    return
                
                _logger.info("📦 %s livraison(s) récupérée(s)", len(deliveries))
                
                updated, not_found, errors = 0, 0, 0
                
                for delivery in deliveries:
                    try:
                        order_ref = delivery.get("NumeroCommande")
                        
                        if not order_ref:
                            _logger.warning("⚠️ Numero commande manquante")
                            errors += 1
                            continue
                        
                        # Rechercher la commande
                        orders = self.env['purchase.order'].search([
                                    ('name', '=', order_ref),
                                    ('sage_x3_submitted', '=', True),
                                    ('sage_x3_validated', '=', False)
                                ])
                        for order in orders:
                            if order:
                                order.write({
                                    'sage_x3_delivery_received': True,
                                    'sage_x3_delivery_date': fields.Datetime.now(),
                                })
                                
                                order.message_post(
                                    body=f"✅ Livraison confirmée par SAGE X3<br/>ID: {delivery.get('id')}",
                                    subject="Livraison SAGE X3"
                                )
                                
                                _logger.info("🔄 Livraison confirmée: %s", order_ref)
                                updated += 1
                            else:
                                _logger.warning("⚠️ Commande %s introuvable", order_ref)
                                not_found += 1
                            
                    except Exception as e:
                        errors += 1
                        _logger.error("❌ Erreur traitement livraison: %s", str(e))
                
                _logger.info("=" * 50)
                _logger.info("=== RÉSUMÉ IMPORT LIVRAISONS ===")
                _logger.info("✅ Mises à jour    : %s", updated)
                _logger.info("⚠️ Non trouvées   : %s", not_found)
                _logger.info("❌ Erreurs        : %s", errors)
                _logger.info("=" * 50)
                
            else:
                _logger.error("❌ Erreur récupération: HTTP %s", response.status_code)
                
        except Exception as e:
            _logger.exception("🚨 Échec récupération livraisons SAGE X3: %s", str(e))
            raise UserError(f"Erreur récupération livraisons: {str(e)}")

    def action_import_deliveries(self):
        """Action manuelle pour importer les livraisons"""
        try:
            self.import_deliveries_from_sage_x3()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Succès',
                    'message': 'Livraisons importées avec succès',
                    'type': 'success',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Erreur',
                    'message': f'Erreur: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }