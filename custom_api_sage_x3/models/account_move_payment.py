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
ACCOUNTING_URL = f"{BASE_URL}/api/Accounting/entries/batch"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

TIMEOUT = 30
MAX_RETRIES = 3


class AccountMoveSageX3(models.Model):
    _inherit = "account.move"

    # ============================================================================
    # PARTIE 1: FACTURES HORS POS (Envoi DIRECT sans wizard)
    # ============================================================================

    def action_send_all_classic_invoices_to_sage_x3(self):
        """
        Envoyer toutes les factures classiques non envoyées - ENVOI DIRECT
        SÉCURITÉ: Uniquement les factures des sociétés de l'utilisateur
        """
        # Filtrer par les sociétés auxquelles l'utilisateur a accès
        company = self.env.company
        
        return True

    @api.model
    def _process_bulk_send_classic_invoices_to_sage_x3(self, invoice_ids):
        """
        Traite l'envoi en masse des factures classiques
        """
        invoices = self.browse(invoice_ids)
        
        success_count = 0
        error_count = 0
        errors = []
        _logger.info("📊 Nombre de factures: %s", len(invoices))
        
        for idx, invoice in enumerate(invoices, 1):
            try:
                
                invoice._send_single_invoice_to_sage_x3()
                success_count += 1
                
                if idx % 10 == 0:
                    self.env.cr.commit()
                
            except Exception as e:
                error_count += 1
                errors.append(f"{invoice.name}: {str(e)}")
                _logger.error("❌ Erreur facture %s: %s", invoice.name, str(e))
        
        self.env.cr.commit()
        _logger.info("📊 Succès: %s | Erreurs: %s", success_count, error_count)
        
        return {
            'success': success_count,
            'errors': error_count,
            'error_details': errors
        }

    def _send_single_invoice_to_sage_x3(self):
        """
        Envoie une facture classique (hors POS) à SAGE X3
        """
        self.ensure_one()
        
        # Vérifications
        if self.state != 'posted':
            raise UserError("Seules les factures validées peuvent être envoyées")
        
        if self.move_type != 'out_invoice':
            raise UserError("Seules les factures clients peuvent être envoyées")
        
        if not self.partner_id.customer_id:
            raise UserError(
                f"Le client {self.partner_id.name} n'a pas de code tiers SAGE X3 configuré.\n"
                f"Veuillez renseigner le champ 'Code tiers SAGE X3' sur la fiche client."
            )
        
        company = self.company_id
        
        # Préparer les données
        accounting_data = self._prepare_invoice_entry(self)
        
        if not accounting_data:
            raise UserError("Impossible de préparer les données de la facture")
        
        # Authentification
        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")
        
        # Envoi
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = self._safe_post(ACCOUNTING_URL, headers, accounting_data)

        _logger.error("STATUS: %s", response.status_code)
        _logger.error("HEADERS: %s", response.headers)
        _logger.error("BODY: %s", response.text)
        _logger.error("REPONSE TEST: %s", response)
        
        if response.status_code in (200, 201):

            if not response.text:
                raise UserError("Réponse vide reçue de Sage X3")

            # Sage renvoie un fichier texte, pas du JSON
            response_text = response.text.strip()

            # Extraire la référence depuis la ligne G
            first_line = response_text.splitlines()[0]
            parts = first_line.split(";")

            # Format: G;FACLI;;SIEGE;110226;VTE;FACLI_SAN_INV_2026_00012;XOF;STDCO
            if len(parts) >= 7:
                piece_number = parts[6]
            else:
                piece_number = accounting_data['entries'][0]['piece']['reference']

            self.write({
                'sage_x3_sent': True,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_piece_type': 'FACLI',
                'sage_x3_piece_number': piece_number,
            })

        else:
            error_msg = f"Erreur HTTP {response.status_code}: {response.text}"
            _logger.error("❌ ERREUR: %s", error_msg)
            raise UserError(error_msg)

    def _prepare_invoice_entry(self, invoice):
        """
        Prépare les données d'une facture classique pour SAGE X3
        
        Structure:
        - DÉBIT: Compte client (411xxx) avec thirdParty
        - CRÉDIT: Comptes de produits (701xxx, 706xxx, etc.) selon les lignes
        """
        lines = []
        
        # 1. LIGNE DÉBIT - Compte client (total TTC)
        if not invoice.partner_id.customer_id:
            raise UserError(f"Client {invoice.partner_id.name} sans code tiers SAGE X3")
        
        third_party = invoice.partner_id.customer_id.strip()
        
        # Compte client de débit
        receivable_account = invoice.company_id.sage_x3_account_customer_default_id
        if not receivable_account:
            raise UserError(f"Compte client non configuré pour {invoice.partner_id.name}")
        
        lines.append({
            "account": receivable_account.code,
            "label": f"Facture {invoice.name}",
            "sense": 1,  # Débit
            "amount": invoice.amount_total,
            "thirdParty": third_party
        })
        
        # 2. LIGNES CRÉDIT - Produits (regroupés par compte)
        product_lines = defaultdict(float)
        
        for line in invoice.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note'):
                continue
            
            # Compte de produit
            account = line.account_id
            if not account:
                _logger.warning("⚠️ Ligne sans compte: %s", line.name)
                continue
            
            # Montant TTC 
            amount = line.price_total
            
            if amount == 0:
                continue
            
            # Regrouper par compte
            product_lines[account.code] += amount
        
        # Créer les lignes de crédit
        credit_account = invoice.company_id.sage_x3_account_sale_id
        if not credit_account:
            raise UserError(f"Compte vente non configuré pour {invoice.partner_id.name}")
        
        for account_code, amount in sorted(product_lines.items()):
            if amount > 0:
                lines.append({
                    "account": credit_account.code,
                    "label": f"Ventes {invoice.invoice_date.strftime('%d/%m/%Y')}",
                    "sense": -1,  # Crédit
                    "amount": amount,
                    "thirdParty": ""
                })
        
        # 4. Construction de la pièce
        company = invoice.company_id
        
        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")
        
        if not company.sage_x3_journal_sale:
            raise UserError(f"Journal de vente SAGE X3 non configuré pour {company.name}")
        
        company_code = company.code if hasattr(company, 'code') and company.code else company.lib_company.upper()
        
        piece = {
            "type": "FACLI",
            "numero": "",
            "site": company.sage_x3_site,
            "date": invoice.invoice_date.strftime("%Y-%m-%d"),
            "journal": company.sage_x3_journal_sale,
            "reference": f"FACLI_{company_code}_{invoice.name.replace('/', '_')}",
            "devise": "XOF",
            "transaction": "STDCO"
        }
        
        entry = {
            "piece": piece,
            "lines": lines
        }
        
        return {"entries": [entry]}

    def _authenticate_sage_x3(self):
        """Authentification SAGE X3"""
        try:
            _logger.debug("🔐 Authentification SAGE X3...")
            response = requests.post(
                AUTH_URL,
                json={"username": USERNAME, "password": PASSWORD},
                timeout=15
            )
            
            if response.status_code in (200, 201):
                token = response.json().get("token")
                if token:
                    return token
                else:
                    return None
            else:
                _logger.error("❌ Échec authentification: HTTP %s", response.status_code)
                return None
                
        except Exception as e:
            _logger.error("❌ Erreur authentification: %s", str(e))
            return None

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """POST avec retry automatique"""
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                _logger.debug("📡 Tentative %s/%s: POST %s", attempt + 1, MAX_RETRIES, url)
                
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                
                if response.status_code in (200, 201):
                    _logger.debug("✅ Requête réussie")
                    return response
                else:
                    _logger.warning("⚠️  HTTP %s (tentative %s/%s)", response.status_code, attempt + 1, MAX_RETRIES)
                    last_exception = Exception(f"HTTP {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                _logger.warning("⏱️  Timeout (tentative %s/%s)", attempt + 1, MAX_RETRIES)
                last_exception = Exception("Timeout")
                
            except Exception as e:
                _logger.warning("❌ Erreur (tentative %s/%s): %s", attempt + 1, MAX_RETRIES, str(e))
                last_exception = e
            
            # Attendre avant de réessayer (sauf dernière tentative)
            if attempt < MAX_RETRIES - 1:
                import time
                wait_time = 2 * (attempt + 1)
                _logger.info("⏳ Attente %ss avant nouvelle tentative...", wait_time)
                time.sleep(wait_time)
        
        # Échec après tous les retries
        if last_exception:
            raise last_exception
        else:
            raise Exception("Échec après retries")


# ============================================================================
# PAIEMENTS CLIENTS (REGCLI) - ENVOI DIRECT
# ============================================================================

class AccountPaymentSageX3(models.Model):
    _inherit = "account.payment"

    def action_send_all_pending_payments_to_sage_x3(self):
        """
        Envoyer TOUS les paiements clients non envoyés - ENVOI DIRECT
        SÉCURITÉ: Uniquement les paiements des sociétés de l'utilisateur
        """
        # Filtrer par les sociétés auxquelles l'utilisateur a accès
        company = self.env.company
        
        pending_payments = self.search([
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state', '=', 'paid'),
            ('sage_x3_sent', '=', False),
            # SÉCURITÉ: Uniquement les sociétés autorisées
            ('company_id', '=', company.id),
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
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    },
                }
            }
        
        # ENVOI DIRECT - Pas de wizard
        try:
            return self._process_bulk_send_payments_to_sage_x3(pending_payments.ids)
                 
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '❌ Erreur',
                    'message': f'Erreur lors de l\'envoi: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    },
                }
            }

    @api.model
    def _process_bulk_send_payments_to_sage_x3(self, payment_ids):
        """Traite l'envoi en masse des paiements"""
        payments = self.browse(payment_ids)
        
        success_count = 0
        error_count = 0
        errors = []
        _logger.info("📊 Nombre de paiements: %s", len(payments))
        
        for idx, payment in enumerate(payments, 1):
            try:
                
                payment._send_payment_to_sage_x3()
                success_count += 1
                
                if idx % 10 == 0:
                    self.env.cr.commit()
                
            except Exception as e:
                error_count += 1
                errors.append(f"{payment.name}: {str(e)}")
                _logger.error("❌ Erreur paiement %s: %s", payment.name, str(e))
        
        self.env.cr.commit()
        
        return {
            'success': success_count,
            'errors': error_count,
            'error_details': errors
        }

    def _send_payment_to_sage_x3(self):
        """
        Envoie un règlement client à SAGE X3 (type REGCLI)
        
        Structure:
        - DÉBIT: Compte de trésorerie (banque/caisse selon le journal)
        - CRÉDIT: Compte client (411xxx) avec thirdParty
        """
        self.ensure_one()
        
        # Vérifications
        if self.state != 'paid':
            raise UserError("Seuls les paiements validés peuvent être envoyés")
        
        if self.payment_type != 'inbound':
            raise UserError("Seuls les paiements entrants peuvent être envoyés")
        
        if self.partner_type != 'customer':
            raise UserError("Seuls les paiements clients peuvent être envoyés")
        
        if not self.partner_id.customer_id:
            raise UserError(
                f"Le client {self.partner_id.name} n'a pas de code tiers SAGE X3 configuré.\n"
                f"Veuillez renseigner le champ 'Code tiers SAGE X3' sur la fiche client."
            )
        
        company = self.company_id
        third_party = self.partner_id.customer_id.strip()
        
        # Préparer les lignes
        lines = []
        
        # 1. LIGNE DÉBIT - Compte de trésorerie (banque/caisse)
        debit_account = self.journal_id.default_account_id
        if not debit_account:
            raise UserError(f"Compte par défaut manquant sur le journal {self.journal_id.name}")
        
        lines.append({
            "account": debit_account.code,
            "label": f"Règlement {self.partner_id.name}",
            "sense": 1,  # Débit
            "amount": self.amount,
            "thirdParty": ""
        })
        
        # 2. LIGNE CRÉDIT - Compte client
        credit_account = company.sage_x3_account_customer_default_id
        if not credit_account:
            raise UserError(f"Compte client non configuré pour {self.partner_id.name}")
        
        lines.append({
            "account": credit_account.code,
            "label": f"Règlement {self.partner_id.name}",
            "sense": -1,  # Crédit
            "amount": self.amount,
            "thirdParty": third_party
        })
        
        # 3. Construction de la pièce
        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")
        
        
        journal_payment = self.journal_id.name
        company_code = company.code if hasattr(company, 'code') and company.code else company.lib_company.upper()
        
        piece = {
            "type": "REGCLI",
            "numero": "",
            "site": company.sage_x3_site,
            "date": self.date.strftime("%Y-%m-%d"),
            "journal": journal_payment,
            "reference": f"REGCLI_{company_code}_{self.name.replace('/', '_')}",
            "devise": "XOF",
            "transaction": "STDCO"
        }
        
        entry = {
            "piece": piece,
            "lines": lines
        }
        
        accounting_data = {"entries": [entry]}
        # Envoyer à SAGE X3
        _logger.info("📦 Données JSON:")
        _logger.info(json.dumps(accounting_data, indent=2, ensure_ascii=False))
        
        # Authentification
        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")
        
        # Envoi
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = self._safe_post(ACCOUNTING_URL, headers, accounting_data)

        if response.status_code in (200, 201):

            if not response.text:
                raise UserError("Réponse vide reçue de Sage X3")

            # Sage renvoie un fichier texte, pas du JSON
            response_text = response.text.strip()

            # Extraire la référence depuis la ligne G
            first_line = response_text.splitlines()[0]
            parts = first_line.split(";")

            # Format: G;FACLI;;SIEGE;110226;VTE;FACLI_SAN_INV_2026_00012;XOF;STDCO
            if len(parts) >= 7:
                piece_number = parts[6]
            else:
                piece_number = accounting_data['entries'][0]['piece']['reference']

            self.write({
                'sage_x3_sent': True,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_piece_type': 'REGCLI',
                'sage_x3_piece_number': piece_number,
            })
        else:
            error_msg = f"Erreur HTTP {response.status_code}: {response.text}"
            _logger.error("❌ ERREUR: %s", error_msg)
            raise UserError(error_msg)

    def _authenticate_sage_x3(self):
        """Authentification SAGE X3"""
        try:
            response = requests.post(
                AUTH_URL,
                json={"username": USERNAME, "password": PASSWORD},
                timeout=15
            )
            
            if response.status_code in (200, 201):
                token = response.json().get("token")
                if token:
                    _logger.debug("✅ Authentification réussie")
                    return token
                else:
                    _logger.error("❌ Token manquant dans la réponse")
                    return None
            else:
                _logger.error("❌ Échec authentification: HTTP %s", response.status_code)
                return None
                
        except Exception as e:
            _logger.error("❌ Erreur authentification: %s", str(e))
            return None

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """POST avec retry automatique"""
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                _logger.debug("📡 Tentative %s/%s: POST %s", attempt + 1, MAX_RETRIES, url)
                
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                
                if response.status_code in (200, 201):
                    _logger.debug("✅ Requête réussie")
                    return response
                else:
                    _logger.warning("⚠️  HTTP %s (tentative %s/%s)", 
                                  response.status_code, attempt + 1, MAX_RETRIES)
                    last_exception = Exception(f"HTTP {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                _logger.warning("⏱️  Timeout (tentative %s/%s)", attempt + 1, MAX_RETRIES)
                last_exception = Exception("Timeout")
                
            except Exception as e:
                _logger.warning("❌ Erreur (tentative %s/%s): %s", attempt + 1, MAX_RETRIES, str(e))
                last_exception = e
            
            # Attendre avant de réessayer (sauf dernière tentative)
            if attempt < MAX_RETRIES - 1:
                import time
                wait_time = 2 * (attempt + 1)
                _logger.info("⏳ Attente %ss avant nouvelle tentative...", wait_time)
                time.sleep(wait_time)
        
        # Échec après tous les retries
        if last_exception:
            raise last_exception
        else:
            raise Exception("Échec après retries")
