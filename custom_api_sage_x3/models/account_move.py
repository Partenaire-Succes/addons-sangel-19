import json
import logging
from datetime import datetime
from collections import defaultdict

from odoo import fields, models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMoveSageX3(models.Model):
    """
    Intégration SAGE X3 pour account.move.

    ┌──────────┬──────────────────────────────────────────────────────────────────┐
    │ FACLI    │ Facture client  (out_invoice hors POS)                           │
    │ AVCLI    │ Avoir client    (out_refund  hors POS)                           │
    ├──────────┼──────────────────────────────────────────────────────────────────┤
    │ ENCAI    │ Récap journalier caisse :                                        │
    │          │  [1] Total ventes POS (aucun flag) → 1 seule ligne groupée       │
    │          │  [2] Règlements clients (account.payment) → 1 ligne/paiement     │
    │          │  [3] Écart de caisse → 1 ligne (si ≠ 0)                          │
    │          │  [4] Contrepartie caisse → 1 ligne (sens=-1)                     │
    ├──────────┼──────────────────────────────────────────────────────────────────┤
    │ DECAI    │ Récap journalier hors caisse (is_limit=True) :                   │
    │          │  Flags exclusifs (un seul actif à la fois) :                     │
    │          │  is_limit          → individuel, avec tiers,       sens=-1       │
    │          │  is_food           → individuel, avec tiers,       sens=-1       │
    │          │  is_bank_card      → groupé par compte, sans tiers, sens=-1      │
    │          │  is_cheque         → groupé par compte, sans tiers, sens=-1      │
    │          │  is_titre_paiement → groupé par compte, sans tiers, sens=-1      │
    │          │  Contrepartie caisse → 1 ligne totale (sens=+1)                  │
    └──────────┴──────────────────────────────────────────────────────────────────┘

    Champs requis sur res.company :
        sage_x3_site                        ex: "SIEGE"
        sage_x3_journal_caisse              ex: "CYL"
        sage_x3_journal_sale                ex: "VTE"
        sage_x3_account_sale_id             ex: 70116000  (compte vente)
        sage_x3_account_customer_default_id ex: 41110000  (compte client)
        sage_x3_account_caisse_id           ex: 57110005  (compte caisse contrepartie)
        sage_x3_account_ecart_caisse_id     ex: 77820000  (compte écart de caisse)
    """
    _name    = 'account.move'
    _inherit = ['account.move', 'sage.x3.mixin']

    # =========================================================================
    # POINT D'ENTRÉE — Wizard
    # =========================================================================

    def action_send_all_pending_to_sage_x3(self):
        return {
            'type':      'ir.actions.act_window',
            'name':      'Sélectionner la période',
            'res_model': 'sage.x3.send.wizard',
            'view_mode': 'form',
            'target':    'new',
        }

    # =========================================================================
    # PARTIE 1 — POS + RÈGLEMENTS : ENCAI + DECAI (récap journalier)
    # =========================================================================

    @api.model
    def _process_bulk_send_to_sage_x3(self, date_from, date_to, company_ids):
        """
        Envoi groupé par société et par jour.
        Chaque journée produit jusqu'à 2 écritures : ENCAI et/ou DECAI.
        Les account.payment du jour sont inclus dans l'ENCAI.
        """
        success_count = 0
        error_count   = 0
        errors        = []

        for company_id in company_ids:
            company = self.env['res.company'].browse(company_id)
            if not company.exists():
                _logger.error("❌ Société ID %s introuvable", company_id)
                continue

            current_date    = fields.Date.from_string(date_from)
            end_date        = fields.Date.from_string(date_to)
            company_success = 0
            company_errors  = 0

            while current_date <= end_date:
                try:
                    data = self._prepare_daily_entry(company, current_date)

                    if data and data.get('ecritures'):
                        self._send_daily_to_sage_x3_api(data, company, current_date)
                        success_count   += 1
                        company_success += 1
                        _logger.info(
                            "✅ %s — %s : %s écriture(s) envoyée(s)",
                            company.name, current_date, len(data['ecritures'])
                        )
                    else:
                        _logger.info("ℹ️  %s — %s : aucune donnée",
                                     company.name, current_date)

                    self.env.cr.commit()

                except Exception as e:
                    error_count    += 1
                    company_errors += 1
                    msg = f"{company.name} — {current_date}: {str(e)}"
                    errors.append(msg)
                    _logger.error("❌ %s", msg, exc_info=True)

                current_date = fields.Date.add(current_date, days=1)

            _logger.info("📊 %s : %s succès / %s erreurs",
                         company.name, company_success, company_errors)

        return {'success': success_count, 'errors': error_count, 'error_details': errors}


    def get_pos_lines_grouped_by_tva(self, pos_sessions):

        if not pos_sessions:
            return {}

        lines = self.env['pos.order.line'].search([
            ('order_id.session_id', 'in', pos_sessions.ids),
            ('order_id.payment_ids.payment_method_id.is_limit', '=', False),
            ('tax_ids', '!=', False),
        ])

        grouped_tax = defaultdict(float)

        for line in lines:
            tax_res = line.tax_ids.compute_all(
                line.price_unit,
                quantity=line.qty,
                product=line.product_id,
            )

            for tax in tax_res['taxes']:
                taux = round(tax['rate'] * 100, 2)  # taux fiable
                grouped_tax[taux] += tax['amount']

        return grouped_tax

    def get_pos_lines_total_ht(self, pos_sessions):
        """
        Retourne le montant total HT des lignes POS
        (hors taxes, basé sur Odoo compute_all pour être fiable)
        """

        if not pos_sessions:
            return 0.0

        lines = self.env['pos.order.line'].search([
            ('order_id.session_id', 'in', pos_sessions.ids),
            ('order_id.payment_ids.payment_method_id.is_limit', '=', False),
        ])

        total_ht = 0.0

        for line in lines:
            # Calcul officiel Odoo
            tax_res = line.tax_ids.compute_all(
                line.price_unit,
                quantity=line.qty,
                product=line.product_id,
            )

            total_ht += tax_res['total_excluded']  # HT

        return round(total_ht, 2)

    def _prepare_daily_entry(self, company, target_date):
        """
        Prépare les écritures ENCAI et/ou DECAI pour UNE société, UN jour.

        Règle de routage par flag (flags exclusifs — un seul actif à la fois) :
        ┌──────────────────────┬────────┬──────────────────────────────────────┐
        │ Flag mode paiement   │ Pièce  │ Regroupement                         │
        ├──────────────────────┼────────┼──────────────────────────────────────┤
        │ Aucun flag           │ ENCAI  │ Groupé → 1 seule ligne totale        │
        │ is_limit             │ DECAI  │ Individuel, avec tiers               │
        │ is_food              │ DECAI  │ Individuel, avec tiers               │
        │ is_bank_card         │ DECAI  │ Groupé par compte (1 ligne/compte)   │
        │ is_cheque            │ DECAI  │ Groupé par compte (1 ligne/compte)   │
        │ is_titre_paiement    │ DECAI  │ Groupé par compte (1 ligne/compte)   │
        └──────────────────────┴────────┴──────────────────────────────────────┘
        """
        dt_min = datetime.combine(target_date, datetime.min.time())
        dt_max = datetime.combine(target_date, datetime.max.time())

        # Sessions POS du jour
        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('start_at',   '>=', dt_min),
            ('start_at',   '<=', dt_max),
        ])

        # Règlements clients du jour (account.payment hors POS)
        account_payments = self.env['account.payment'].search([
            ('company_id',   '=',  company.id),
            ('payment_type', '=',  'inbound'),
            ('partner_type', '=',  'customer'),
            ('partner_id',   '!=', False),
            ('pos_order_id', '=',  False),
            ('state',        '=',  'paid'),
            ('sage_x3_sent', '=',  False),
            ('date',         '>=', target_date),
            ('date',         '<=', target_date),
        ])

        if not pos_sessions and not account_payments:
            return None

        # Bloquer si une session est encore ouverte
        if pos_sessions:
            open_sessions = pos_sessions.filtered(lambda s: s.state != 'closed')
            if open_sessions:
                names = ', '.join(open_sessions.mapped('name'))
                raise UserError(
                    f"Sessions POS encore ouvertes ({company.name} — {target_date}) :\n"
                    f"{names}\n\nFermez toutes les sessions avant d'envoyer à SAGE X3."
                )

        # Configuration société (fail-fast)
        site         = company.sage_x3_site
        journal      = company.sage_x3_journal_caisse
        sale_account = company.sage_x3_account_sale_id
        cust_account = company.sage_x3_account_customer_default_id
        caisse_acct  = company.sage_x3_account_caisse_id
        sale_tva_9   = company.sage_x3_account_sale_tva_9_id
        sale_tva_18  = company.sage_x3_account_sale_tva_18_id
        magasin      = self._get_company_code(company)
        date_yy      = target_date.strftime("%d%m%y")
        date_fr      = target_date.strftime("%d/%m/%Y")

        for label, val in [
            ("Site SAGE X3",           site),
            ("Journal caisse",         journal),
            ("Compte vente",           sale_account),
            ("Compte client",          cust_account),
            ("Compte caisse",          caisse_acct),
        ]:
            if not val:
                raise UserError(f"{label} non configuré pour {company.name}")

        # =====================================================================
        # COLLECTE DES PAIEMENTS POS
        #
        # ENCAI :
        #   encai_pos_total      → somme des paiements sans flag (1 ligne totale)
        #
        # DECAI individuel (is_limit, is_food) :
        #   decai_individual     → liste de lignes, 1 par paiement, avec tiers
        #
        # DECAI groupé par compte (is_bank_card, is_cheque, is_titre_paiement) :
        #   decai_grouped_by_compte → {compte_code: {"montant": float, "libelle": str}}
        #   → 1 seule ligne par compte dans le DECAI final
        # =====================================================================
        encai_pos_total         = 0.0
        decai_individual_limit  = []
        decai_individual_food   = []
        decai_grouped_by_compte = {}   # clé = code compte, valeur = {montant, libelle}

        if pos_sessions:
            # Encaissement total
            encai_pos_total = self.get_pos_lines_total_ht(pos_sessions)

        for session in pos_sessions:
            payments = self.env['pos.payment'].search([
                ('session_id',   '=',  session.id),
                ('sage_x3_sent', '=',  False),
            ])

            for payment in payments:
                method = payment.payment_method_id
                if not method:
                    _logger.warning("⚠️ Paiement sans méthode ignore — session %s",
                                session.name)
                    continue

                amount = abs(payment.amount)
                if amount == 0:
                    continue

                pay_account = method.journal_id.default_account_id
                if not pay_account:
                    if method.is_limit:
                        pay_account = cust_account
                    else:
                        _logger.error(
                            "❌ Mode '%s' ignoré : aucun compte comptable sur son journal. "
                            "Corrigez dans PdV > Configuration > Modes de paiement.",
                            method.name
                        )
                        continue

                partner    = payment.partner_id
                tiers_code = (
                    partner.customer_id.strip()
                    if partner and partner.customer_id else ""
                )
                pay_date   = (
                    payment.payment_date.strftime("%d/%m/%Y")
                    if payment.payment_date else date_fr
                )
                order_ref  = (
                    payment.pos_order_id.name
                    if getattr(payment, 'pos_order_id', False)
                    else (payment.name or '')
                )

                # ── Routage par flag (exclusifs) ──────────────────────────────
                if method.is_limit:
                    # Individuel avec tiers
                    decai_individual_limit.append({
                        "compte":  pay_account.code,
                        "libelle": f"{method.name} DU {pay_date}",
                        "montant": amount,
                        "tiers":   tiers_code,
                    })

                else:
                    
                    if method.is_food:
                        # Individuel avec tiers
                        partner_name = partner.name if partner else ''
                        decai_individual_food.append({
                            "compte":  pay_account.code,
                            "libelle": f"CREDIT ALIMENT {partner_name} N°{order_ref}",
                            "montant": amount,
                            "tiers":   tiers_code,
                        })

                    elif method.is_bank_card:
                        # Groupé par compte — 1 seule ligne par compte dans le DECAI
                        compte = pay_account.code
                        if compte not in decai_grouped_by_compte:
                            decai_grouped_by_compte[compte] = {
                                "montant": 0.0,
                                "libelle": f"CB {method.name} DU {date_fr}",
                            }
                        decai_grouped_by_compte[compte]["montant"] += amount

                    elif method.is_cheque:
                        # Groupé par compte — 1 seule ligne par compte dans le DECAI
                        compte = pay_account.code
                        if compte not in decai_grouped_by_compte:
                            decai_grouped_by_compte[compte] = {
                                "montant": 0.0,
                                "libelle": f"CHQ {method.name} DU {date_fr}",
                            }
                        decai_grouped_by_compte[compte]["montant"] += amount

                    elif method.is_titre_paiement:
                        # Groupé par compte — 1 seule ligne par compte dans le DECAI
                        compte = pay_account.code
                        if compte not in decai_grouped_by_compte:
                            decai_grouped_by_compte[compte] = {
                                "montant": 0.0,
                                "libelle": f"PAIEMT {method.name} DU {date_fr}",
                            }
                        decai_grouped_by_compte[compte]["montant"] += amount

        # =====================================================================
        # CONSTRUCTION ENCAI
        # [1] Ventes POS (aucun flag)  → 1 seule ligne totale
        # [2] Règlements clients       → 1 ligne / account.payment
        # [3] Écart de caisse          → 1 ligne si ≠ 0
        # [4] Contrepartie caisse      → 1 ligne (sens=-1)
        # =====================================================================
        lignes_encai = []
        total_encai  = 0.0
        total_tax_encai = 0.0

        # [1] Ventes POS groupées
        if encai_pos_total > 0:
            lignes_encai.append(self._build_ligne(
                site    = site,
                compte  = sale_account.code,
                sens    = -1,
                montant = round(encai_pos_total, 2),
                libelle = f"VENTES {magasin} DU {date_fr}",
            ))
            total_encai += encai_pos_total

        grouped_tax_compte = self.get_pos_lines_grouped_by_tva(pos_sessions)

        for taux, montant in sorted(grouped_tax_compte.items()):

            taux_int = int(round(taux))

            if taux_int == 18:
                compte = sale_tva_18
            elif taux_int == 9:
                compte = sale_tva_9
            else:
                continue  # ignore les autres taux

            if montant > 0:
                lignes_encai.append(self._build_ligne(
                    site    = site,
                    compte  = compte.code if hasattr(compte, 'code') else compte,
                    sens    = 1,
                    montant = round(montant, 2),
                    libelle = f"TVA {taux_int}% {date_fr}",
                ))

                total_tax_encai += montant

        # [2] Règlements clients (account.payment) — 1 ligne par paiement
        for pmt in account_payments:
            if not pmt.partner_id:
                _logger.warning(
                    "⚠️ Règlement %s ignoré : aucun partenaire associé.",
                    pmt.name
                )
                continue
            if not pmt.partner_id.customer_id:
                _logger.warning(
                    "⚠️ Règlement %s ignoré : '%s' sans code tiers SAGE X3. "
                    "Renseignez-le dans Contacts > %s.",
                    pmt.name, pmt.partner_id.name, pmt.partner_id.name
                )
                continue

            journal_name = pmt.journal_id.name or ''
            ref_pmt      = pmt.name or ''
            libelle_pmt  = (
                f"REGLT {journal_name} N°{ref_pmt}/{pmt.partner_id.name}"
            )[:50]

            lignes_encai.append(self._build_ligne(
                site    = site,
                compte  = cust_account.code,
                sens    = -1,
                montant = round(pmt.amount, 2),
                libelle = libelle_pmt,
                tiers   = pmt.partner_id.customer_id.strip(),
            ))
            total_encai += pmt.amount

        # [4] Contrepartie caisse (sens=1)
        if lignes_encai and total_encai > 0:
            lignes_encai.append(self._build_ligne(
                site    = site,
                compte  = caisse_acct.code,
                sens    = 1,
                montant = round(total_encai, 2),
                libelle = f"CAISSE {magasin} DU {date_fr}",
            ))

        # =====================================================================
        # CONSTRUCTION DECAI
        # [1] is_limit   → individuel, avec tiers,        sens=-1
        # [2] is_food    → individuel, avec tiers,        sens=-1
        # [3] is_bank_card      → 1 ligne / compte,       sens=-1
        # [4] is_cheque         → 1 ligne / compte,       sens=-1
        # [5] is_titre_paiement → 1 ligne / compte,       sens=-1
        # [6] Contrepartie caisse → 1 ligne totale (sens=+1)
        # =====================================================================
        lignes_decai = []
        total_decai  = 0.0

        # Lignes individuelles (is_limit), triées (compte, tiers)
        for line in sorted(decai_individual_limit,
                           key=lambda x: (x['compte'], x.get('tiers', ''))):
            lignes_decai.append(self._build_ligne(
                site    = site,
                compte  = line['compte'],
                sens    = -1,
                montant = round(line['montant'], 2),
                libelle = line['libelle'],
                tiers   = line.get('tiers', ''),
            ))
            total_decai += line['montant']

        # Lignes individuelles (is_food), triées (compte, tiers)
        for line in sorted(decai_individual_food,
                           key=lambda x: (x['compte'], x.get('tiers', ''))):
            lignes_decai.append(self._build_ligne(
                site    = site,
                compte  = line['compte'],
                sens    = -1,
                montant = round(line['montant'], 2),
                libelle = line['libelle'],
                tiers   = line.get('tiers', ''),
            ))
            total_decai += line['montant']    

        # [3]+[4]+[5] Lignes groupées par compte (is_bank_card, is_cheque, is_titre_paiement)
        # → 1 seule ligne par code compte, triées par code compte
        for compte, data in sorted(decai_grouped_by_compte.items()):
            montant = data['montant']
            if montant > 0:
                lignes_decai.append(self._build_ligne(
                    site    = site,
                    compte  = compte,
                    sens    = -1,
                    montant = round(montant, 2),
                    libelle = data['libelle'],
                ))
                total_decai += montant

        # [6] Contrepartie caisse DECAI (sens=+1, inverse de ENCAI)
        if lignes_decai and total_decai > 0:
            lignes_decai.append(self._build_ligne(
                site    = site,
                compte  = caisse_acct.code,
                sens    = 1,
                montant = round(total_decai, 2),
                libelle = f"CAISSE {magasin} DU {date_fr}",
            ))

        # =====================================================================
        # ASSEMBLAGE FINAL
        # =====================================================================
        ecritures = []

        if lignes_encai and total_encai > 0:
            ecritures.append(self._build_ecriture(
                type_piece  = "ENCAI",
                site        = site,
                date_ddmmyy = date_yy,
                journal     = journal,
                libelle     = f"ENCAISSEMENT CAISSE {magasin} DU {date_fr}",
                lignes      = lignes_encai,
            ))

        if lignes_decai and total_decai > 0:
            ecritures.append(self._build_ecriture(
                type_piece  = "DECAI",
                site        = site,
                date_ddmmyy = date_yy,
                journal     = journal,
                libelle     = f"DECAISSEMENT CAISSE {magasin} DU {date_fr}",
                lignes      = lignes_decai,
            ))

        if not ecritures:
            _logger.info("ℹ️  Aucune écriture pour %s le %s",
                         company.name, target_date)
            return None

        return {"ecritures": ecritures}

    def _send_daily_to_sage_x3_api(self, accounting_data, company, target_date):
        """Envoie ENCAI + DECAI à SAGE X3 et marque les enregistrements."""

        config = self._get_sage_x3_config()

        _logger.info(
            "📦 JSON POS (%s — %s):\n%s",
            company.name, target_date,
            json.dumps(accounting_data, indent=2, ensure_ascii=False),
        )

        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = self._safe_post(config['accounting_url'], headers, accounting_data)

        if response.status_code not in (200, 201):
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")

        # 🔥 Extraction complète
        x3_results = self._extract_x3_results(response, f"POS_{target_date}")

        errors = []
        success_pieces = []
        success_messages = []

        for res in x3_results:
            if res["piece"]:
                success_pieces.append(res["piece"])
                success_messages.append(res["message"])
            else:
                errors.append(res["message"])

        # ❌ S'il y a au moins une erreur → on bloque tout
        if errors:
            raise UserError(
                "❌ SAGE X3 a rejeté certaines écritures :\n" + "\n".join(errors)
            )

        # ✅ Succès
        piece_numbers = ", ".join(success_pieces)
        full_message = "\n".join(success_messages)

        _logger.info("✅ SAGE X3 OK — Pièces : %s", piece_numbers)

        # 🔥 Passage message + pièces
        self._mark_daily_as_sent(company, target_date, piece_numbers, full_message)

    def _mark_daily_as_sent(self, company, target_date, piece_numbers, message):
        """Marque les paiements comme envoyés avec numéro + message."""

        dt_min = datetime.combine(target_date, datetime.min.time())
        dt_max = datetime.combine(target_date, datetime.max.time())

        # ======================
        # 🔹 POS PAYMENTS
        # ======================
        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('start_at', '>=', dt_min),
            ('start_at', '<=', dt_max),
        ])

        pos_payments = self.env['pos.payment'].search([
            ('session_id', 'in', pos_sessions.ids),
            ('sage_x3_sent', '=', False),
        ])

        if pos_payments:
            pos_payments.write({
                'sage_x3_sent': True,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_piece_number': piece_numbers,
                'message': message,
            })
            _logger.info("✅ %s paiement(s) POS marqués", len(pos_payments))

        # ======================
        # 🔹 ACCOUNT PAYMENTS
        # ======================
        account_payments = self.env['account.payment'].search([
            ('company_id', '=', company.id),
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state', '=', 'paid'),
            ('sage_x3_sent', '=', False),
            ('date', '=', target_date),
        ])

        if account_payments:
            account_payments.write({
                'sage_x3_sent': True,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_piece_number': piece_numbers,
                'message': message,
            })
            _logger.info("✅ %s règlement(s) clients marqués", len(account_payments))

    # =========================================================================
    # PARTIE 2 — FACLI / AVCLI (factures et avoirs hors POS)
    # =========================================================================

    @api.model
    def _process_bulk_send_classic_invoices_to_sage_x3(self, invoice_ids):
        """Envoi en masse des factures (FACLI) et avoirs (AVCLI) hors POS."""
        invoices      = self.browse(invoice_ids)
        success_count = 0
        error_count   = 0
        errors        = []

        for idx, invoice in enumerate(invoices, 1):
            try:
                invoice._send_single_invoice_to_sage_x3()
                success_count += 1
                if idx % 10 == 0:
                    self.env.cr.commit()
            except Exception as e:
                error_count += 1
                errors.append(f"{invoice.name}: {str(e)}")
                _logger.error("❌ %s: %s", invoice.name, str(e))

        self.env.cr.commit()
        _logger.info("📊 FACLI/AVCLI — Succès: %s | Erreurs: %s",
                     success_count, error_count)
        return {'success': success_count, 'errors': error_count,
                'error_details': errors}

    def _send_single_invoice_to_sage_x3(self):
        """Envoie une facture (FACLI) ou un avoir (AVCLI) à SAGE X3."""
        self.ensure_one()

        if self.state != 'posted':
            raise UserError("Seules les pièces validées peuvent être envoyées.")
        if self.move_type not in ('out_invoice', 'out_refund'):
            raise UserError("Seules les factures et avoirs clients sont acceptés.")
        if not self.partner_id.customer_id:
            raise UserError(
                f"Le client {self.partner_id.name} n'a pas de code tiers SAGE X3.\n"
                f"Renseignez le champ 'Code tiers SAGE X3' sur la fiche client."
            )

        config          = self._get_sage_x3_config()
        accounting_data = self._prepare_invoice_entry(self)

        _logger.info(
            "📦 JSON %s",
            json.dumps(accounting_data, indent=2, ensure_ascii=False),
        )

        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

        response = self._safe_post(config['accounting_url'], headers, accounting_data)

        if response.status_code not in (200, 201):
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")

        response_data = response.json()

        if not isinstance(response_data, list):
            raise UserError("Réponse inattendue de SAGE X3 (format non-liste)")

        target_date = response_data[0]['numero']
        x3_results = self._extract_x3_results(response, f"POS_{target_date}")

        errors = []
        success_pieces = []
        success_messages = []

        for res in x3_results:
            if res["piece"]:
                success_pieces.append(res["piece"])
                success_messages.append(res["message"])
            else:
                errors.append(res["message"])

        # ❌ S'il y a au moins une erreur → on bloque tout
        if errors:
            self.write({
                'sage_x3_sent':         False,
                'sage_x3_sent_date':    fields.Datetime.now(),
                'sage_x3_error':        errors,
            })
            raise UserError("\n".join(errors))

        # ✅ Succès
        piece_numbers = ", ".join(success_pieces)
        full_message = "\n".join(success_messages)

        _logger.info("✅ SAGE X3 OK — Pièces : %s", piece_numbers)

        self.write({
            'sage_x3_sent':         True,
            'sage_x3_sent_date':    fields.Datetime.now(),
            'sage_x3_piece_number': piece_numbers,
            'sage_x3_response':     full_message,
            'sage_x3_error':        False,
        })

    def _compute_tva(self, montant_ttc, taux):
        if not montant_ttc:
            return 0.0

        # Sécurisation du taux (18 ou 0.18)
        taux = taux / 100 if taux > 1 else taux

        tva = montant_ttc * taux / (1 + taux)
        return round(tva, 2)


    def _prepare_invoice_entry(self, invoice):
        company     = invoice.company_id
        is_refund   = (invoice.move_type == 'out_refund')
        type_piece  = "AVCLI" if is_refund else "FACLI"

        sens_client = -1 if is_refund else  1
        sens_vente  =  1 if is_refund else -1

        receivable  = company.sage_x3_account_customer_default_id
        sale_acct   = company.sage_x3_account_sale_id
        sale_tva_9  = company.sage_x3_account_sale_tva_9_id
        sale_tva_18 = company.sage_x3_account_sale_tva_18_id
        site        = company.sage_x3_site
        journal     = company.sage_x3_journal_sale

        # 🔒 Vérification config
        for label, val in [
            ("Compte client", receivable),
            ("Compte vente",  sale_acct),
            ("Site SAGE X3",  site),
            ("Journal vente", journal),
            ("Compte TVA 9%",  sale_tva_9),
            ("Compte TVA 18%", sale_tva_18),
        ]:
            if not val:
                raise UserError(f"{label} non configuré pour {company.name}")

        third_party = (invoice.partner_id.customer_id or "").strip()
        date_yy     = invoice.invoice_date.strftime("%d%m%y")
        date_fr     = invoice.invoice_date.strftime("%d/%m/%Y")
        magasin     = self._get_company_code(company)
        lignes      = []

        # =========================
        # Ligne client
        # =========================
        lignes.append(self._build_ligne(
            site    = site,
            compte  = receivable.code,
            sens    = sens_client,
            montant = round(invoice.amount_total, 2),
            libelle = f"{type_piece} {invoice.name}",
            tiers   = third_party,
        ))

        # =========================
        # TVA
        # =========================
        tax_facli = defaultdict(float)

        for line in invoice.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note'):
                continue

            # ⚠️ Correction : gérer plusieurs taxes
            for tax in line.tax_ids:
                if tax.amount == 9:
                    tax_val = self._compute_tva(line.price_total, 0.09)
                    tax_facli[sale_tva_9] += tax_val

                elif tax.amount == 18:
                    tax_val = self._compute_tva(line.price_total, 0.18)
                    tax_facli[sale_tva_18] += tax_val

        # =========================
        # Ligne vente (HT)
        # =========================
        if not invoice.amount_untaxed:
            raise UserError(f"Aucune ligne de produit valide sur {invoice.name}")

        if invoice.amount_untaxed > 0:
            lignes.append(self._build_ligne(
                site    = site,
                compte  = sale_acct.code,
                sens    = sens_vente,
                montant = round(invoice.amount_untaxed, 2),
                libelle = f"VENTES {date_fr}",
            ))

        # =========================
        # Lignes TVA
        # =========================
        for account, amount in tax_facli.items():
            if amount > 0:
                taux = 9 if account == sale_tva_9 else 18
                
                lignes.append(self._build_ligne(
                    site    = site,
                    compte  = account.code,
                    sens    = sens_vente,
                    montant = round(amount, 2),
                    libelle = f"TVA {taux}% {date_fr}",
                ))

        # =========================
        # Écriture finale
        # =========================
        return {
            "ecritures": [
                self._build_ecriture(
                    type_piece  = type_piece,
                    site        = site,
                    date_ddmmyy = date_yy,
                    journal     = journal,
                    libelle     = f"{type_piece} {magasin} {invoice.name}",
                    lignes      = lignes,
                )
            ]
        }