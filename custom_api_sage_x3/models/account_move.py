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

    def action_send_all_pending_to_sage_x3(self):
        """
        Bouton pour envoyer TOUTES les factures de la journée groupées par société
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sélectionner la période',
            'res_model': 'sage.x3.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {}
        }

    @api.model
    def _process_bulk_send_to_sage_x3(self, date_from, date_to, company_ids):
        """
        Traite l'envoi groupé par société et par jour
        IMPORTANT: Chaque société envoie UNIQUEMENT ses propres données
        """
        success_count = 0
        error_count = 0
        errors = []
        
        # Pour chaque société (isolation stricte)
        for company_id in company_ids:
            company = self.env['res.company'].browse(company_id)
            
            # Vérification que la société existe et est active
            if not company.exists():
                _logger.error("❌ Société ID %s introuvable", company_id)
                continue
            
            try:
                # Générer les pièces jour par jour POUR CETTE SOCIÉTÉ UNIQUEMENT
                current_date = fields.Date.from_string(date_from)
                end_date = fields.Date.from_string(date_to)
                
                company_success = 0
                company_errors = 0
                
                while current_date <= end_date:
                    try:
                        
                        # Préparer les données de la journée POUR CETTE SOCIÉTÉ
                        accounting_data = self._prepare_daily_entry(company, current_date)
                        
                        if accounting_data and accounting_data.get('entries'):
                            # Envoyer à SAGE X3
                            self._send_daily_to_sage_x3_api(accounting_data, company, current_date)
                            success_count += 1
                            company_success += 1
                            _logger.info("✅ %s - %s: Envoyé avec succès", company.name, current_date)
                        else:
                            _logger.info("ℹ️  %s - %s: Aucune donnée à envoyer", company.name, current_date)
                        
                        # Commit après chaque journée pour éviter de perdre les données
                        self.env.cr.commit()
                        
                    except Exception as e:
                        error_count += 1
                        company_errors += 1
                        error_msg = f"{company.name} - {current_date}: {str(e)}"
                        errors.append(error_msg)
                        _logger.error("❌ ERREUR %s", error_msg, exc_info=True)
                        # Continue avec le jour suivant même en cas d'erreur
                    
                    # Passer au jour suivant
                    current_date = fields.Date.add(current_date, days=1)
                
                _logger.info("")
                _logger.info("📊 Résumé société %s: %s succès / %s erreurs", 
                           company.name, company_success, company_errors)
                    
            except Exception as e:
                error_count += 1
                error_msg = f"{company.name} (erreur générale): {str(e)}"
                errors.append(error_msg)
                _logger.error("❌ ERREUR SOCIÉTÉ %s", error_msg, exc_info=True)
        
        return {
            'success': success_count,
            'errors': error_count,
            'error_details': errors
        }

    def _prepare_daily_entry(self, company, target_date):
        """
        Prépare l'écriture comptable groupée pour UNE journée d'UNE société
        
        IMPORTANT: 
        - Regroupe TOUTES les sessions POS (toutes les caisses) de la journée
        - UNIQUEMENT pour la société passée en paramètre (isolation stricte)
        - Basé sur pos.session.payment_ids
        - PAIEMENTS COMPTANT (is_limit=False): GROUPÉS par mode de paiement
        - PAIEMENTS CRÉDIT (is_limit=True): AUCUN REGROUPEMENT - une ligne par paiement
        
        Paramètres:
            company: res.company - La société (UNE SEULE)
            target_date: date - La date (UN SEUL jour)
            
        Retourne:
            dict: Données au format SAGE X3 ou None si pas de données
        """
        _logger.info("🔍 Recherche sessions POS pour %s le %s", company.name, target_date)
        
        # ISOLATION STRICTE: Ne récupérer QUE les sessions de CETTE société
        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),  # ← FILTRE SOCIÉTÉ OBLIGATOIRE
            ('start_at', '>=', datetime.combine(target_date, datetime.min.time())),
            ('start_at', '<=', datetime.combine(target_date, datetime.max.time())),
            ('state', '=', 'closed'),
        ])
        
        if not pos_sessions:
            _logger.info("ℹ️  Aucune session POS fermée pour %s le %s", company.name, target_date)
            return None
        
        # Regroupement des paiements
        # payments_cash: {(account_code, payment_method_name): total_amount} - GROUPÉ
        # payments_credit_lines: [liste de lignes] - AUCUN REGROUPEMENT
        payments_cash = defaultdict(float)
        payments_credit_lines = []  # Liste de lignes individuelles (pas de regroupement)
        
        total_payments_processed = 0
        
        # Parcourir TOUTES les sessions (toutes les caisses de cette société)
        for session in pos_sessions:
            session_total = 0
            payments = self.env['pos.payment'].search([
                ('session_id', '=', session.id)
            ])
            
            for payment in payments:
                payment_method = payment.payment_method_id
                
                if not payment_method:
                    _logger.warning("⚠️  Paiement sans méthode dans session %s", session.name)
                    continue
                
                # Compte de débit = journal du moyen de paiement
                debit_account = payment_method.journal_id.default_account_id
                
                if not debit_account:
                    _logger.warning("⚠️  Compte de débit manquant pour '%s' (session %s)", 
                                  payment_method.name, session.name)
                    if payment_method.is_limit:
                        # Fallback pour paiements crédit sans compte configuré
                        debit_account = company.sage_x3_account_customer_default_id
                        if not debit_account:
                            _logger.error("❌ Compte client par défaut manquant pour %s", company.name)
                            continue
                    else:
                        continue
                
                amount = abs(payment.amount)
                
                if amount == 0:
                    continue
                
                # Vérifier si c'est un paiement crédit (client en compte)
                if payment_method.is_limit:
                    # PAIEMENT CRÉDIT: AUCUN REGROUPEMENT
                    # → Créer UNE LIGNE par paiement (pas d'accumulation)
                    partner = payment.partner_id
                    
                    if partner and partner.customer_id:
                        third_party = partner.customer_id.strip()
                        
                        # Créer directement la ligne (pas d'accumulation)
                        label = f"{payment_method.name} du {payment.payment_date.strftime('%d/%m/%Y')}"
                        
                        payments_credit_lines.append({
                            "account": debit_account.code,
                            "label": label,
                            "sense": 1,  # Débit
                            "amount": amount,
                            "thirdParty": third_party,
                            "payment_method": payment_method.name,
                            "client": partner.name
                        })
                    else:
                        # Pas de compte client configuré
                        _logger.warning("⚠️  Client '%s' sans customer_id (session %s) - traité comme comptant", 
                                      partner.name if partner else "Inconnu", session.name)
                        # Traiter comme comptant
                        payment_key = (debit_account.code, payment_method.name)
                        payments_cash[payment_key] += amount
                else:
                    # PAIEMENT COMPTANT: GROUPÉ par mode de paiement
                    payment_key = (debit_account.code, payment_method.name)
                    payments_cash[payment_key] += amount
                
                session_total += amount
                total_payments_processed += 1
        
        # Vérifier qu'on a bien des données
        if not payments_cash and not payments_credit_lines:
            _logger.warning("⚠️  Aucun paiement valide trouvé pour %s le %s", company.name, target_date)
            return None
        
        # Construction des lignes d'écriture
        lines = []
        
        # 1. LIGNES DÉBIT - Paiements comptant (GROUPÉS par mode de paiement)
        for (account_code, payment_method_name), amount in sorted(payments_cash.items()):
            if amount > 0:
                # Utiliser directement le nom du moyen de paiement
                label = f"{payment_method_name} du {target_date.strftime('%d/%m/%Y')}"
                
                lines.append({
                    "account": account_code,
                    "label": label,
                    "sense": 1,  # Débit
                    "amount": amount,
                    "thirdParty": ""
                })
        
        # 2. LIGNES DÉBIT - Paiements crédit (AUCUN REGROUPEMENT - liste directe)
        
        if payments_credit_lines:
            # Trier par compte, puis par client
            payments_credit_lines_sorted = sorted(
                payments_credit_lines, 
                key=lambda x: (x['account'], x['thirdParty'])
            )
            
            for idx, credit_line in enumerate(payments_credit_lines_sorted, 1):
                # Ajouter directement la ligne (déjà créée)
                lines.append({
                    "account": credit_line['account'],
                    "label": credit_line['label'],
                    "sense": credit_line['sense'],
                    "amount": credit_line['amount'],
                    "thirdParty": credit_line['thirdParty']
                })
        
        # Calculer le total
        total_amount = sum(line['amount'] for line in lines)
        
        if total_amount == 0:
            _logger.warning("⚠️  Total nul pour %s le %s", company.name, target_date)
            return None
        
        # 3. LIGNE CRÉDIT - Total des ventes (contrepartie unique)
        sale_account = company.sage_x3_account_sale_id
        if not sale_account:
            raise UserError(
                f"Configuration manquante pour {company.name}\n"
                f"Le compte de vente SAGE X3 n'est pas configuré.\n"
                f"Veuillez le configurer dans: Paramètres > Sociétés > {company.name}"
            )
        
        lines.append({
            "account": sale_account.code,
            "label": f"Ventes {target_date.strftime('%d/%m/%Y')}",
            "sense": -1,  # Crédit
            "amount": total_amount,
            "thirdParty": ""
        })
        
        # 4. Construction de la pièce comptable
        # Vérifier la configuration de la société
        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")
        
        if not company.sage_x3_journal_sale:
            raise UserError(f"Journal de vente SAGE X3 non configuré pour {company.name}")
        
        # Générer une référence unique
        # Format: FACLI_[CODE_SOCIETE]_YYYYMMDD
        company_code = company.code if hasattr(company, 'code') and company.code else company.name[:3].upper()
        
        piece = {
            "type": "FACLI",
            "numero": "",
            "site": company.sage_x3_site,
            "date": target_date.strftime("%Y-%m-%d"),
            "journal": company.sage_x3_journal_sale,
            "reference": f"FACLI_{company_code}_{target_date.strftime('%Y%m%d')}",
            "devise": "XOF",
            "transaction": "STDCO"
        }
        
        entry = {
            "piece": piece,
            "lines": lines
        }
        
        return {"entries": [entry]}

    def _send_daily_to_sage_x3_api(self, accounting_data, company, target_date):
        """
        Envoie les données journalières à l'API SAGE X3
        
        Paramètres:
            accounting_data: dict - Données au format SAGE X3
            company: res.company - Société concernée
            target_date: date - Date de la journée
        """
        try:
            _logger.info("📦 Données JSON POS:")
            _logger.info(json.dumps(accounting_data, indent=2, ensure_ascii=False))
            
            # 1. Authentification
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec de l'authentification SAGE X3")
            
            # 2. Envoi des données
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            response = self._safe_post(ACCOUNTING_URL, headers, accounting_data)
            
            # 3. Traitement de la réponse
            if response.status_code in (200, 201):
                response_data = response.json()
                
                # Récupérer le numéro de pièce généré par SAGE X3
                piece_number = response_data.get('pieceNumber', 
                                                accounting_data['entries'][0]['piece']['reference'])
                
                _logger.info("✅ SUCCÈS SAGE X3")
                _logger.info("   • Numéro de pièce: %s", piece_number)
                _logger.info("   • Réponse: %s", json.dumps(response_data, indent=2, ensure_ascii=False))
                
                # 4. Marquer les factures comme envoyées
                self._mark_invoices_as_sent(company, target_date, piece_number)
                
                return True
            else:
                error_msg = f"Erreur HTTP {response.status_code}: {response.text}"
                _logger.error("❌ ERREUR SAGE X3: %s", error_msg)
                raise UserError(error_msg)
                
        except Exception as e:
            error_msg = f"Erreur lors de l'envoi à SAGE X3: {str(e)}"
            _logger.exception("❌ %s", error_msg)
            raise

    def _mark_invoices_as_sent(self, company, target_date, piece_number):
        """
        Marque les factures de la journée comme envoyées à SAGE X3
        
        IMPORTANT: Ne marque QUE les factures de la société concernée
        """
        invoices = self.search([
            ('company_id', '=', company.id),  # ← Isolation par société
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '=', target_date),
            ('sage_x3_sent', '=', False),
        ])
        
        if invoices:
            invoices.write({
                'sage_x3_sent': True,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_piece_type': 'FACLI',
                'sage_x3_piece_number': piece_number,
            })
            
            _logger.info("✅ %s facture(s) marquée(s) comme envoyée(s) à SAGE X3", len(invoices))
        else:
            _logger.info("ℹ️  Aucune facture à marquer pour %s le %s", company.name, target_date)

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
                wait_time = 2 * (attempt + 1)  # Backoff progressif: 2s, 4s, 6s
                _logger.info("⏳ Attente %ss avant nouvelle tentative...", wait_time)
                time.sleep(wait_time)
        
        # Échec après tous les retries
        if last_exception:
            raise last_exception
        else:
            raise Exception("Échec après retries")