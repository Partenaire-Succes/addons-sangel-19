import requests
import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import json
from datetime import datetime, date
from collections import defaultdict

_logger = logging.getLogger(__name__)

BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
ACCOUNTING_URL = f"{BASE_URL}/api/Accounting/entries"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

TIMEOUT = 30
MAX_RETRIES = 3


class AccountPaymentSageX3(models.Model):
    _inherit = "account.payment"


    def action_send_payment_to_sage_x3(self):
        """Bouton pour envoyer le paiement à SAGE X3"""
        self.ensure_one()
        
        try:
            self._send_payment_to_sage_x3()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Succès',
                    'message': f'Règlement envoyé à SAGE X3\nN°: {self.sage_x3_piece_number}',
                    'type': 'success',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '❌ Erreur',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def action_send_all_pending_payments_to_sage_x3(self):
        """
        Bouton pour envoyer TOUS les paiements clients non envoyés à SAGE X3
        """
        # Chercher tous les paiements clients validés non envoyés
        pending_payments = self.search([
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state', '=', 'posted'),
            ('sage_x3_sent', '=', False),
        ])
        
        total = len(pending_payments)
        
        if total == 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'ℹ️ Information',
                    'message': 'Aucun paiement à envoyer',
                    'type': 'info',
                }
            }
        
        # Wizard de confirmation
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmer l\'envoi des paiements à SAGE X3',
            'res_model': 'sage.x3.payment.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_count': total,
                'payment_ids': pending_payments.ids,
            }
        }

    @api.model
    def _process_bulk_send_payments_to_sage_x3(self, payment_ids):
        """
        Traite l'envoi en masse des paiements à SAGE X3
        """
        payments = self.browse(payment_ids)
        
        success_count = 0
        error_count = 0
        errors = []
        
        _logger.info("="*80)
        _logger.info("🚀 [BULK] Démarrage envoi en masse de %s paiements à SAGE X3", len(payments))
        _logger.info("="*80)
        
        for idx, payment in enumerate(payments, 1):
            try:
                _logger.info("📤 [%s/%s] Envoi paiement %s", idx, len(payments), payment.name)
                
                payment._send_payment_to_sage_x3()
                success_count += 1
                
                # Commit tous les 10 envois
                if idx % 10 == 0:
                    self.env.cr.commit()
                    _logger.info("💾 Commit intermédiaire après %s paiements", idx)
                
            except Exception as e:
                error_count += 1
                error_msg = f"{payment.name}: {str(e)}"
                errors.append(error_msg)
                _logger.error("❌ [%s/%s] Erreur paiement %s: %s", idx, len(payments), payment.name, str(e))
        
        # Commit final
        self.env.cr.commit()
        
        _logger.info("="*80)
        _logger.info("✅ [BULK] Envoi terminé: %s succès, %s erreurs", success_count, error_count)
        _logger.info("="*80)
        
        return {
            'success': success_count,
            'errors': error_count,
            'error_details': errors
        }

    def action_post(self):
        """Hook après validation du paiement - DÉSACTIVÉ pour envoi manuel uniquement"""
        result = super().action_post()
        
        # ENVOI AUTOMATIQUE DÉSACTIVÉ
        # Les paiements doivent être envoyés manuellement via le bouton
        
        return result

    def _send_payment_to_sage_x3(self):
        """Envoie le règlement client à SAGE X3"""
        self.ensure_one()
        
        # Vérifications
        if self.payment_type != 'inbound' or self.partner_type != 'customer':
            return
        
        if self.state != 'posted':
            raise UserError("Le paiement doit être validé")
        
        if self.sage_x3_sent:
            raise UserError("Ce paiement a déjà été envoyé à SAGE X3")
        
        company = self.company_id
        partner = self.partner_id
        date_piece = self.date or fields.Date.today()
        
        # Déterminer le compte de trésorerie selon le moyen de paiement
        treasury_account = self._get_treasury_account()
        
        # Compte client
        customer_account = partner.property_account_receivable_id
        if not customer_account:
            raise UserError(f"Compte client non configuré pour {partner.name}")
        
        # Third party
        third_party_code = customer_account.code + partner.ref if partner.ref else customer_account.code
        
        # Montant
        amount = abs(self.amount)
        
        lines = [
            {
                "account": treasury_account.code,
                "label": f"Règlement {self.name} - {partner.name}",
                "sense": 1,  # Débit
                "amount": amount,
                "thirdParty": ""
            },
            {
                "account": customer_account.code,
                "label": f"Apurement {self.name}",
                "sense": -1,  # Crédit
                "amount": amount,
                "thirdParty": third_party_code
            }
        ]
        
        # Journal selon le type de paiement
        journal_code = self._get_sage_x3_journal()
        
        piece = {
            "type": "REGCLI",
            "numero": "",
            "site": company.sage_x3_site or "SIEGE",
            "date": date_piece.strftime("%Y-%m-%d"),
            "journal": journal_code,
            "reference": self.name,
            "devise": self.currency_id.name or "XOF",
            "transaction": "STDCO"
        }
        
        entry = {
            "piece": piece,
            "lines": lines
        }
        
        # Lien vers la facture si existe
        if self.reconciled_invoice_ids:
            invoice = self.reconciled_invoice_ids[0]
            entry["linkedInvoice"] = {
                "invoiceReference": invoice.name,
                "invoiceDate": invoice.invoice_date.strftime("%Y-%m-%d") if invoice.invoice_date else ""
            }
        
        accounting_data = {"entries": [entry]}
        
        # Envoyer
        self._send_payment_to_api(accounting_data)

    def _get_treasury_account(self):
        """Récupère le compte de trésorerie selon le moyen de paiement"""
        self.ensure_one()
        company = self.company_id
        
        # Déterminer le type de paiement
        payment_method = self.payment_method_line_id.payment_method_id if self.payment_method_line_id else None
        
        if not payment_method:
            # Utiliser le compte par défaut du journal
            return self.journal_id.default_account_id
        
        # Mapping selon le nom du moyen de paiement
        method_name = payment_method.name.upper()
        
        if 'ESPECE' in method_name or 'CASH' in method_name or 'CAISSE' in method_name:
            return company.sage_x3_account_cash_id
        elif 'CHEQUE' in method_name or 'CHECK' in method_name:
            return company.sage_x3_account_check_id
        elif 'VIREMENT' in method_name or 'TRANSFER' in method_name:
            return company.sage_x3_account_transfer_id
        elif 'MOBILE' in method_name or 'MOMO' in method_name:
            return company.sage_x3_account_mobile_money_id
        elif 'TPE' in method_name or 'CARD' in method_name or 'CARTE' in method_name:
            return company.sage_x3_account_tpe_id
        else:
            # Par défaut, utiliser le compte du journal
            return self.journal_id.default_account_id

    def _get_sage_x3_journal(self):
        """Récupère le code journal SAGE X3 selon le type de paiement"""
        self.ensure_one()
        company = self.company_id
        
        payment_method = self.payment_method_line_id.payment_method_id if self.payment_method_line_id else None
        
        if not payment_method:
            return company.sage_x3_journal_bank or "BQ"
        
        method_name = payment_method.name.upper()
        
        if 'ESPECE' in method_name or 'CASH' in method_name or 'CAISSE' in method_name:
            return company.sage_x3_journal_cash or "CAISSE"
        else:
            return company.sage_x3_journal_bank or "BQ"

    def _send_payment_to_api(self, accounting_data):
        """Envoie le paiement à l'API SAGE X3"""
        self.ensure_one()
        
        try:
            _logger.info("📤 Envoi paiement %s à SAGE X3", self.name)
            
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec authentification SAGE X3")
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = self._safe_post(ACCOUNTING_URL, headers, accounting_data)
            
            if response.status_code in (200, 201):
                response_data = response.json()
                piece_number = response_data.get('pieceNumber', self.name)
                
                self.write({
                    'sage_x3_sent': True,
                    'sage_x3_sent_date': fields.Datetime.now(),
                    'sage_x3_piece_number': piece_number,
                    'sage_x3_error': False,
                })
                
                self.message_post(
                    body=f"<h3>✅ Règlement envoyé à SAGE X3</h3><p>N° Pièce: {piece_number}</p>",
                    subject="✅ SAGE X3"
                )
                
                _logger.info("✅ Paiement %s envoyé: %s", self.name, piece_number)
                return True
            else:
                raise UserError(f"Erreur HTTP {response.status_code}")
                
        except Exception as e:
            error_msg = f"Erreur: {str(e)}"
            self.write({'sage_x3_error': error_msg})
            _logger.exception("❌ %s", error_msg)
            raise

    def _authenticate_sage_x3(self):
        """Authentification SAGE X3"""
        try:
            response = requests.post(
                AUTH_URL,
                json={"username": USERNAME, "password": PASSWORD},
                timeout=15
            )
            return response.json().get("token") if response.status_code in (200, 201) else None
        except:
            return None

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """POST avec retry"""
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
            except:
                pass
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(2)
        return requests.post(url, headers=headers, json=data, timeout=timeout)

