import requests
import logging as logger
from odoo import fields, models, api, _
from odoo.exceptions import UserError
import json
from datetime import datetime

_logger = logger.getLogger(__name__)

BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
ACCOUNTING_ENTRIES_URL = f"{BASE_URL}/api/Accounting/entries/batch"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

TIMEOUT = 30
MAX_RETRIES = 3


class AccountMoveSageX3(models.Model):
    _inherit = "account.move"

    # Champs de suivi SAGE X3
    sage_x3_sent = fields.Boolean(
        string="Envoyé à SAGE X3",
        default=False,
        readonly=True,
        copy=False
    )
    sage_x3_sent_date = fields.Datetime(
        string="Date envoi SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_entry_id = fields.Char(
        string="ID Écriture SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_response = fields.Text(
        string="Réponse SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_error = fields.Text(
        string="Erreur SAGE X3",
        readonly=True,
        copy=False
    )

    def action_post(self):
        """Surcharge pour envoyer à SAGE X3 après validation"""
        res = super(AccountMoveSageX3, self).action_post()
        
        # Envoyer automatiquement à SAGE X3 après validation
        for move in self:
            if not move.sage_x3_sent and move.state == 'posted':
                try:
                    move.send_to_sage_x3()
                except Exception as e:
                    _logger.error("❌ Erreur envoi SAGE X3 pour %s: %s", move.name, str(e))
                    move.write({'sage_x3_error': str(e)})
        
        return res

    def send_to_sage_x3(self):
        """Envoie l'écriture comptable vers SAGE X3"""
        self.ensure_one()
        
        if self.sage_x3_sent:
            _logger.warning("⚠️ Écriture %s déjà envoyée", self.name)
            return True
        
        if self.state != 'posted':
            raise UserError("Seules les écritures validées peuvent être envoyées à SAGE X3")
        
        try:
            _logger.info("📤 Envoi écriture %s vers SAGE X3...", self.name)
            
            # 1. Authentification
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec authentification SAGE X3")
            
            # 2. Préparation des données
            entry_data = self._prepare_accounting_entry()
            
            # 3. Envoi
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            _logger.info("📦 Données envoyées:\n%s", json.dumps(entry_data, indent=2))
            
            response = self._safe_post(ACCOUNTING_ENTRIES_URL, headers, entry_data)
            
            if response.status_code in (200, 201):
                response_data = response.json()
                
                # Traiter la réponse
                if isinstance(response_data, list) and len(response_data) > 0:
                    result = response_data[0]
                    success = result.get("success", False)
                    message = result.get("message", "")
                    
                    if success:
                        self.write({
                            'sage_x3_sent': True,
                            'sage_x3_sent_date': fields.Datetime.now(),
                            'sage_x3_entry_id': result.get("id"),
                            'sage_x3_response': message,
                            'sage_x3_error': False,
                        })
                        
                        _logger.info("✅ Écriture %s envoyée avec succès", self.name)
                        
                        self.message_post(
                            body=f"✅ Écriture envoyée à SAGE X3 \n Message: {message}",
                            subject="Envoi SAGE X3"
                        )
                        return True
                    else:
                        raise UserError(f"SAGE X3 a rejeté l'écriture: {message}")
                else:
                    raise UserError("Format de réponse invalide")
            else:
                raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            error_msg = f"Erreur envoi SAGE X3: {str(e)}"
            _logger.exception("❌ %s", error_msg)
            
            self.write({'sage_x3_error': error_msg})
            
            self.message_post(
                body=f"❌ Erreur envoi SAGE X3: {error_msg}",
                subject="Erreur SAGE X3"
            )
            
            raise

    def _authenticate_sage_x3(self):
        """Authentification SAGE X3"""
        try:
            auth_data = {"username": USERNAME, "password": PASSWORD}
            response = requests.post(AUTH_URL, json=auth_data, timeout=15)
            
            if response.status_code in (200, 201):
                return response.json().get("token")
            return None
        except Exception as e:
            _logger.exception("❌ Auth SAGE X3: %s", str(e))
            return None

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """POST avec retry"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ Tentative %s: HTTP %s", attempt, response.status_code)
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Tentative %s: %s", attempt, str(e))
            
            if attempt < MAX_RETRIES:
                import time
                time.sleep(2)
        
        return requests.post(url, headers=headers, json=data, timeout=timeout)

    def _prepare_accounting_entry(self):
        """
        Prépare l'écriture comptable pour SAGE X3
        Format conforme à l'API SAGE X3
        """
        self.ensure_one()
        
        # Déterminer le type de pièce selon le type d'écriture
        piece_type = "FACLI"  # Par défaut : Facture client
        if self.move_type == 'out_invoice':
            piece_type = "FACLI"
        elif self.move_type == 'in_invoice':
            piece_type = "FACFR"  # Facture fournisseur
        elif self.move_type == 'out_refund':
            piece_type = "AVCLI"  # Avoir client
        elif self.move_type == 'in_refund':
            piece_type = "AVFR"   # Avoir fournisseur
        elif self.move_type == 'entry':
            piece_type = "OD"     # Opération diverse
        
        # Préparer les lignes d'écriture
        lines = []
        for line in self.line_ids:
            if line.display_type in ('line_section', 'line_note'):
                continue
            
            # Déterminer le sens : 1 = débit, -1 = crédit
            sense = 1 if line.debit > 0 else -1
            amount = line.debit if line.debit > 0 else line.credit
            
            line_data = {
                "account": line.account_id.code or "",
                "label": (line.name or "")[:50],  # Limiter à 50 caractères
                "sense": sense,
                "amount": amount,
                "thirdParty": line.partner_id.ref or "" if line.partner_id else ""
            }
            lines.append(line_data)
        
        # Informations de la pièce
        piece = {
            "type": piece_type,
            "numero": "",  # SAGE X3 génère automatiquement
            "site": self.company_id.name or "SIEGE",
            "date": self.date.strftime("%Y-%m-%d") if self.date else datetime.now().strftime("%Y-%m-%d"),
            "journal": self.journal_id.code or "",
            "reference": self.name or "",
            "devise": self.currency_id.name if self.currency_id else "XOF",
            "transaction": "STDCO"  # Transaction standard
        }
        
        # Date d'échéance (si facture client/fournisseur)
        due_date_data = None
        if self.move_type in ['out_invoice', 'in_invoice'] and self.invoice_date_due:
            # Déterminer le mode de paiement
            payment_mode = "VIR"  # Par défaut : virement
            if self.partner_id.property_payment_term_id:
                payment_term = self.partner_id.property_payment_term_id.name.upper()
                if "CHEQUE" in payment_term or "CHQ" in payment_term:
                    payment_mode = "CHQ"
                elif "ESPECE" in payment_term or "ESP" in payment_term:
                    payment_mode = "ESP"
                elif "CARTE" in payment_term:
                    payment_mode = "CB"
            
            # Adresse du tiers
            third_party_address = ""
            if self.partner_id:
                partner_ref = self.partner_id.ref or self.partner_id.name
                partner_city = self.partner_id.city or ""
                if partner_ref and partner_city:
                    third_party_address = f"ADR-{partner_ref}-{partner_city}".upper()
            
            due_date_data = {
                "paymentMode": payment_mode,
                "thirdParty": third_party_address,
                "dueDate": self.invoice_date_due.strftime("%Y-%m-%d")
            }
        
        # Construction de l'entrée
        entry = {
            "piece": piece,
            "lines": lines
        }
        
        # Ajouter dueDate seulement si présent
        if due_date_data:
            entry["dueDate"] = due_date_data
        
        return {"entries": [entry]}

    def action_send_to_sage_x3(self):
        """Action manuelle pour envoyer à SAGE X3"""
        self.ensure_one()
        
        if self.state != 'posted':
            raise UserError("L'écriture doit être validée")
        
        try:
            self.send_to_sage_x3()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Succès',
                    'message': 'Écriture envoyée à SAGE X3',
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
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }

    def action_reset_sage_x3(self):
        """Réinitialiser le statut SAGE X3"""
        self.ensure_one()
        
        self.write({
            'sage_x3_sent': False,
            'sage_x3_error': False,
            'sage_x3_response': False,
        })
        
        self.message_post(body="🔄 Statut SAGE X3 réinitialisé", subject="SAGE X3")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Info',
                'message': 'Statut réinitialisé',
                'type': 'info',
                'sticky': True,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }