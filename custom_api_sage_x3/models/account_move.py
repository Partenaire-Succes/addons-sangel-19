import logging
import json
import time
from datetime import datetime
from collections import defaultdict

from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMoveSageX3(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'sage.x3.mixin']

    # =========================================================================
    # PARTIE 1 : RÉCAP POS (pièce journalière par caisse)
    # =========================================================================

    def action_send_all_pending_to_sage_x3(self):
        """Ouvre le wizard de sélection de période."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sélectionner la période',
            'res_model': 'sage.x3.send.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def _process_bulk_send_to_sage_x3(self, date_from, date_to, company_ids):
        """
        Envoi groupé des récaps POS, société par société, jour par jour.
        Chaque société n'envoie QUE ses propres données (isolation stricte).
        """
        success_count = 0
        error_count = 0
        errors = []

        for company_id in company_ids:
            company = self.env['res.company'].browse(company_id)

            if not company.exists():
                _logger.error("❌ Société ID %s introuvable", company_id)
                continue

            current_date = fields.Date.from_string(date_from)
            end_date = fields.Date.from_string(date_to)
            company_success = 0
            company_errors = 0

            while current_date <= end_date:
                try:
                    accounting_data = self._prepare_daily_entry(company, current_date)

                    if accounting_data and accounting_data.get('entries'):
                        self._send_daily_to_sage_x3_api(accounting_data, company, current_date)
                        success_count += 1
                        company_success += 1
                        _logger.info("✅ %s — %s : envoyé avec succès", company.name, current_date)
                    else:
                        _logger.info("ℹ️  %s — %s : aucune donnée", company.name, current_date)

                    self.env.cr.commit()

                except Exception as e:
                    error_count += 1
                    company_errors += 1
                    msg = f"{company.name} — {current_date}: {str(e)}"
                    errors.append(msg)
                    _logger.error("❌ %s", msg, exc_info=True)

                current_date = fields.Date.add(current_date, days=1)

            _logger.info(
                "📊 Société %s : %s succès / %s erreurs",
                company.name, company_success, company_errors
            )

        return {'success': success_count, 'errors': error_count, 'error_details': errors}

    def _prepare_daily_entry(self, company, target_date):
        """
        Prépare la pièce comptable journalière pour UNE société (toutes caisses).

        Règles métier :
        - Paiements COMPTANT (is_limit=False) → groupés par mode de paiement
        - Paiements CRÉDIT  (is_limit=True)   → une ligne par paiement (pas de regroupement)
        - Lève UserError si une session est encore ouverte (bloquant)
        """
        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('start_at', '>=', datetime.combine(target_date, datetime.min.time())),
            ('start_at', '<=', datetime.combine(target_date, datetime.max.time())),
        ])

        if not pos_sessions:
            return None

        # 🔴 Bloquer si une session est encore ouverte
        open_sessions = pos_sessions.filtered(lambda s: s.state != 'closed')
        if open_sessions:
            session_names = ', '.join(open_sessions.mapped('name'))
            raise UserError(
                f"Sessions POS encore ouvertes pour {company.name} le {target_date} :\n"
                f"{session_names}\n\n"
                f"Fermez toutes les sessions avant d'envoyer les données à SAGE X3."
            )

        # --- Collecte des paiements ---
        payments_cash = defaultdict(float)          # groupés : {(account_code, method_name): total}
        payments_credit_lines = []                  # non groupés : une entrée par paiement

        for session in pos_sessions:
            payments = self.env['pos.payment'].search([
                ('session_id', '=', session.id),
                ('sage_x3_sent', '=', False),
            ])

            for payment in payments:
                payment_method = payment.payment_method_id
                if not payment_method:
                    _logger.warning("⚠️ Paiement sans méthode dans la session %s", session.name)
                    continue

                debit_account = payment_method.journal_id.default_account_id
                amount = abs(payment.amount)

                if amount == 0:
                    continue

                if not debit_account:
                    _logger.warning(
                        "⚠️ Compte de débit manquant pour '%s' (session %s)",
                        payment_method.name, session.name
                    )
                    if payment_method.is_limit:
                        debit_account = company.sage_x3_account_customer_default_id
                        if not debit_account:
                            _logger.error("❌ Compte client par défaut manquant pour %s", company.name)
                            continue
                    else:
                        continue

                if payment_method.is_limit:
                    # --- PAIEMENT CRÉDIT : une ligne par paiement ---
                    partner = payment.partner_id
                    if partner and partner.customer_id:
                        payments_credit_lines.append({
                            "account": debit_account.code,
                            "label": (
                                f"{payment_method.name} du "
                                f"{payment.payment_date.strftime('%d/%m/%Y')}"
                            ),
                            "sense": 1,
                            "amount": amount,
                            "thirdParty": partner.customer_id.strip(),
                        })
                    else:
                        # Pas de code tiers → traité comme comptant
                        _logger.warning(
                            "⚠️ Client '%s' sans customer_id (session %s) — traité comme comptant",
                            partner.name if partner else "Inconnu", session.name
                        )
                        payments_cash[(debit_account.code, payment_method.name)] += amount
                else:
                    # --- PAIEMENT COMPTANT : groupé ---
                    payments_cash[(debit_account.code, payment_method.name)] += amount

        if not payments_cash and not payments_credit_lines:
            _logger.info("ℹ️  Aucun paiement valide pour %s le %s", company.name, target_date)
            return None

        # --- Construction des lignes ---
        lines = []

        # 1. Débits comptant (groupés)
        for (account_code, method_name), amount in sorted(payments_cash.items()):
            if amount > 0:
                lines.append({
                    "account": account_code,
                    "label": f"{method_name} du {target_date.strftime('%d/%m/%Y')}",
                    "sense": 1,
                    "amount": amount,
                    "thirdParty": "",
                })

        # 2. Débits crédit (non groupés, triés par compte puis tiers)
        for credit_line in sorted(payments_credit_lines, key=lambda x: (x['account'], x['thirdParty'])):
            lines.append(credit_line)

        total_amount = sum(line['amount'] for line in lines)

        if total_amount == 0:
            _logger.warning("⚠️ Total nul pour %s le %s", company.name, target_date)
            return None

        # 3. Crédit global (contrepartie vente unique)
        sale_account = company.sage_x3_account_sale_id
        if not sale_account:
            raise UserError(
                f"Compte de vente SAGE X3 non configuré pour {company.name}.\n"
                f"Paramètres > Sociétés > {company.name}"
            )

        lines.append({
            "account": sale_account.code,
            "label": f"Ventes {target_date.strftime('%d/%m/%Y')}",
            "sense": -1,
            "amount": total_amount,
            "thirdParty": "",
        })

        # --- Pièce comptable ---
        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")
        if not company.sage_x3_journal_sale:
            raise UserError(f"Journal de vente SAGE X3 non configuré pour {company.name}")

        company_code = self._get_company_code(company)

        piece = {
            "type": "FACLI",
            "numero": "",
            "site": company.sage_x3_site,
            "date": target_date.strftime("%Y-%m-%d"),
            "journal": company.sage_x3_journal_sale,
            "reference": f"FACLI_{company_code}_{target_date.strftime('%Y%m%d')}",
            "devise": "XOF",
            "transaction": "STDCO",
        }

        return {"entries": [{"piece": piece, "lines": lines}]}

    def _send_daily_to_sage_x3_api(self, accounting_data, company, target_date):
        """Envoie la pièce journalière POS à l'API SAGE X3."""
        config = self._get_sage_x3_config()
        _logger.info("📦 Données JSON POS (%s — %s):", company.name, target_date)
        _logger.info(json.dumps(accounting_data, indent=2, ensure_ascii=False))

        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = self._safe_post(config['accounting_url'], headers, accounting_data)

        if response.status_code in (200, 201):
            piece_number = self._extract_piece_number(
                response, accounting_data['entries'][0]['piece']['reference']
            )
            _logger.info("✅ SUCCÈS SAGE X3 — Pièce : %s", piece_number)
            self._mark_pos_payments_as_sent(company, target_date, piece_number)
        else:
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")

    def _mark_pos_payments_as_sent(self, company, target_date, piece_number):
        """
        Marque les paiements POS de la journée comme envoyés.
        NB : Les factures POS individuelles ne sont PAS marquées ici car la pièce
             envoyée est un récap journalier, pas une facture par facture.
        """
        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('start_at', '>=', datetime.combine(target_date, datetime.min.time())),
            ('start_at', '<=', datetime.combine(target_date, datetime.max.time())),
        ])

        pos_payments = self.env['pos.payment'].search([
            ('session_id', 'in', pos_sessions.ids),
            ('sage_x3_sent', '=', False),
        ])

        if pos_payments:
            pos_payments.write({
                'sage_x3_sent': True,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_piece_number': piece_number,
            })
            _logger.info("✅ %s paiements POS marqués comme envoyés", len(pos_payments))

    # =========================================================================
    # PARTIE 2 : FACTURES CLASSIQUES (hors POS)
    # =========================================================================

    @api.model
    def _process_bulk_send_classic_invoices_to_sage_x3(self, invoice_ids):
        """Envoi en masse des factures classiques (hors POS)."""
        invoices = self.browse(invoice_ids)
        success_count = 0
        error_count = 0
        errors = []

        for idx, invoice in enumerate(invoices, 1):
            try:
                invoice._send_single_invoice_to_sage_x3()
                success_count += 1

                if idx % 10 == 0:
                    self.env.cr.commit()

            except Exception as e:
                error_count += 1
                errors.append(f"{invoice.name}: {str(e)}")
                _logger.error("❌ Facture %s: %s", invoice.name, str(e))

        self.env.cr.commit()
        _logger.info("📊 Factures classiques — Succès: %s | Erreurs: %s", success_count, error_count)

        return {'success': success_count, 'errors': error_count, 'error_details': errors}

    def _send_single_invoice_to_sage_x3(self):
        """Envoie une facture classique (hors POS) à SAGE X3."""
        self.ensure_one()

        if self.state != 'posted':
            raise UserError("Seules les factures validées peuvent être envoyées.")
        if self.move_type != 'out_invoice':
            raise UserError("Seules les factures clients peuvent être envoyées.")
        if not self.partner_id.customer_id:
            raise UserError(
                f"Le client {self.partner_id.name} n'a pas de code tiers SAGE X3.\n"
                f"Renseignez le champ 'Code tiers SAGE X3' sur la fiche client."
            )

        config = self._get_sage_x3_config()
        accounting_data = self._prepare_invoice_entry(self)

        if not accounting_data:
            raise UserError("Impossible de préparer les données de la facture.")

        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = self._safe_post(config['accounting_url'], headers, accounting_data)

        if response.status_code in (200, 201):
            if not response.text:
                raise UserError("Réponse vide reçue de SAGE X3")

            piece_number = self._extract_piece_number(
                response, accounting_data['entries'][0]['piece']['reference']
            )

            self.write({
                'sage_x3_sent': True,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_piece_type': 'FACLI',
                'sage_x3_piece_number': piece_number,
            })
            _logger.info("✅ Facture %s envoyée — Pièce : %s", self.name, piece_number)
        else:
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")

    def _prepare_invoice_entry(self, invoice):
        """
        Prépare la pièce FACLI pour une facture classique.

        Structure :
        - DÉBIT  : Compte client (411xxx) avec thirdParty — montant TTC total
        - CRÉDIT : Compte vente configuré (mapping volontaire vers un seul compte)
                   Une ligne par compte produit distinct (regroupement par compte)
        """
        lines = []
        company = invoice.company_id

        # --- 1. DÉBIT client (total TTC) ---
        third_party = invoice.partner_id.customer_id.strip()

        receivable_account = company.sage_x3_account_customer_default_id
        if not receivable_account:
            raise UserError(
                f"Compte client SAGE X3 non configuré pour {company.name}.\n"
                f"Paramètres > Sociétés > {company.name}"
            )

        lines.append({
            "account": receivable_account.code,
            "label": f"Facture {invoice.name}",
            "sense": 1,
            "amount": invoice.amount_total,
            "thirdParty": third_party,
        })

        # --- 2. CRÉDITS produits (mapping volontaire vers le compte vente global) ---
        credit_account = company.sage_x3_account_sale_id
        if not credit_account:
            raise UserError(
                f"Compte de vente SAGE X3 non configuré pour {company.name}.\n"
                f"Paramètres > Sociétés > {company.name}"
            )

        # Regrouper les montants par compte produit Odoo (pour éviter les doublons de lignes)
        product_lines = defaultdict(float)
        for line in invoice.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note'):
                continue
            if not line.account_id:
                _logger.warning("⚠️ Ligne sans compte dans la facture %s: %s", invoice.name, line.name)
                continue
            if line.price_total == 0:
                continue
            product_lines[line.account_id.code] += line.price_total

        # Une ligne crédit par compte produit Odoo distinct,
        # MAIS toutes pointent vers credit_account.code (mapping volontaire)
        for _odoo_account_code, amount in sorted(product_lines.items()):
            if amount > 0:
                lines.append({
                    "account": credit_account.code,
                    "label": f"Ventes {invoice.invoice_date.strftime('%d/%m/%Y')}",
                    "sense": -1,
                    "amount": amount,
                    "thirdParty": "",
                })

        # --- 3. Pièce comptable ---
        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")
        if not company.sage_x3_journal_sale:
            raise UserError(f"Journal de vente SAGE X3 non configuré pour {company.name}")

        company_code = self._get_company_code(company)

        piece = {
            "type": "FACLI",
            "numero": "",
            "site": company.sage_x3_site,
            "date": invoice.invoice_date.strftime("%y%m%d"),
            "journal": company.sage_x3_journal_sale,
            "reference": f"FACLI_{company_code}_{invoice.name.replace('/', '_')}",
            "devise": "XOF",
            "transaction": "STDCO",
        }

        return {"entries": [{"piece": piece, "lines": lines}]}

    # =========================================================================
    # HELPERS COMMUNS
    # =========================================================================

    def _extract_piece_number(self, response, fallback_reference):
        """
        Extrait le numéro de pièce de la réponse SAGE X3.
        SAGE X3 retourne un fichier texte CSV-like, pas du JSON.
        Format attendu : G;FACLI;;SIEGE;110226;VTE;FACLI_SAN_INV_2026_00012;XOF;STDCO
        """
        try:
            first_line = response.text.strip().splitlines()[0]
            parts = first_line.split(";")
            if len(parts) >= 7 and parts[6]:
                return parts[6]
        except Exception:
            _logger.warning("⚠️ Impossible de lire le numéro de pièce dans la réponse SAGE X3")
        return fallback_reference
