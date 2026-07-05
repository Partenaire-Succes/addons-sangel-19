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
    │ DECAI    │ Récap journalier hors caisse :                                   │
    │          │  is_food           → individuel, avec tiers,       sens=+1       │ƒ
    │          │  is_bank_card      → groupé par compte, sans tiers, sens=+1      │
    │          │  is_cheque         → groupé par compte, sans tiers, sens=+1      │
    │          │  is_titre_paiement → groupé par compte, sans tiers, sens=+1      │
    │          │  Contrepartie caisse → 1 ligne totale (sens=-1)                  │
    └──────────┴──────────────────────────────────────────────────────────────────┘

    Champs requis sur res.company :
        sage_x3_site                        ex: "SIEGE"
        sage_x3_journal_caisse              ex: "CYL"
        sage_x3_journal_sale                ex: "VTE"
        sage_x3_account_sale_id             ex: 70116000  (compte vente)
        sage_x3_account_customer_default_id ex: 41110000  (compte client Abj)
        sage_x3_account_customer_int_default_id ex: 41120000  (compte client Int — FACLI/AVCLI uniquement)
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

                        # ✅ CORRECTION : on lit le retour au lieu de ignorer
                        result = self._send_daily_to_sage_x3_api(data, company, current_date)

                        # Erreurs partielles (certaines écritures ont échoué)
                        if result.get("errors"):
                            for err in result["errors"]:
                                errors.append(err)
                                error_count    += 1
                                company_errors += 1

                        # Succès total ou partiel (au moins 1 pièce créée)
                        if result.get("pieces"):
                            success_count   += 1
                            company_success += 1
                            _logger.info(
                                "✅ %s — %s : pièces créées : %s",
                                company.name, current_date, result["pieces"]
                            )

                    else:
                        _logger.info(
                            "ℹ️  %s — %s : aucune donnée",
                            company.name, current_date
                        )

                except Exception as e:
                    # Erreur bloquante (session ouverte, config manquante, etc.)
                    error_count    += 1
                    company_errors += 1
                    msg = f"{company.name} — {current_date}: {str(e)}"
                    errors.append(msg)
                    _logger.error("❌ %s", msg, exc_info=True)

                current_date = fields.Date.add(current_date, days=1)

            _logger.info(
                "📊 %s : %s succès / %s erreurs",
                company.name, company_success, company_errors
            )

        return {
            'success':       success_count,
            'errors':        error_count,
            'error_details': errors,
        }

    # =========================================================================
    # HELPERS TVA / HT
    # =========================================================================

    def _get_eligible_pos_order_ids(self, pos_sessions):
        """
        Commandes ayant au moins UN paiement à la fois non-limite et non
        encore envoyé (les deux conditions doivent porter sur le MÊME
        paiement). Sans ça, une commande payée moitié cash (déjà envoyée)
        moitié Mise en Compte (FACLI en échec) reste réincluse à l'infini
        dans le CA recalculé, même après l'envoi de sa part cash.
        """
        if not pos_sessions:
            return []

        payments = self.env['pos.payment'].search([
            ('session_id', 'in', pos_sessions.ids),
            ('sage_x3_sent', '=', False),
            ('payment_method_id.is_limit', '=', False),
        ])
        return payments.mapped('pos_order_id').ids

    def get_pos_lines_grouped_by_tva(self, pos_sessions):
        order_ids = self._get_eligible_pos_order_ids(pos_sessions)
        if not order_ids:
            return {}

        lines = self.env['pos.order.line'].search([
            ('order_id', 'in', order_ids),
            ('tax_ids', '!=', False),
        ])

        grouped_tax = defaultdict(float)
        for line in lines:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            tax_res = line.tax_ids.compute_all(
                price,
                quantity=line.qty,
                product=line.product_id,
            )
            for tax_line in tax_res['taxes']:
                tax  = self.env['account.tax'].browse(tax_line['id'])
                taux = tax.amount
                grouped_tax[taux] += tax_line['amount']

        return grouped_tax

    def get_pos_lines_total_ht(self, pos_sessions):
        order_ids = self._get_eligible_pos_order_ids(pos_sessions)
        if not order_ids:
            return 0.0

        lines = self.env['pos.order.line'].search([
            ('order_id', 'in', order_ids),
        ])

        total_ht = 0.0
        for line in lines:
            price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            tax_res   = line.tax_ids.compute_all(
                price,
                quantity=line.qty,
                product=line.product_id,
            )
            total_ht += tax_res['total_excluded']

        return round(total_ht, 2)

    # =========================================================================
    # PRÉPARATION JOURNALIÈRE
    #
    # Retourne :
    #   {
    #     "ecritures":   [...],           ← liste des écritures à envoyer
    #     "payment_map": {                ← mapping index écriture → pos.payment IDs
    #         0: [id1, id2, ...],         ← ENCAI  : paiements cash
    #         1: [id3, id4, ...],         ← DECAI  : food + grouped
    #         2: [id5],                   ← FACLI  : 1 paiement is_limit
    #         3: [id6],                   ← FACLI  : 1 paiement is_limit
    #     }
    #   }
    # =========================================================================

    def _prepare_daily_entry(self, company, target_date):
        dt_min = datetime.combine(target_date, datetime.min.time())
        dt_max = datetime.combine(target_date, datetime.max.time())

        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('sage_x3_sent', '=',  False),
            ('start_at',   '>=', dt_min),
            ('start_at',   '<=', dt_max),
        ])

        # pos_sessions = sessions.filtered(lambda s: s.cash_register_balance_end > 0)

        # FACLI/AVCLI : indépendant de pos_session.sage_x3_sent. Une session
        # déjà marquée envoyée (ENCAI+DECAI ok) peut encore avoir un paiement
        # is_limit resté en échec (FACLI à retenter) — il ne faut pas la
        # perdre simplement parce qu'elle a disparu du filtre ci-dessus.
        facli_payments = self.env['pos.payment'].search([
            ('session_id.company_id',      '=',  company.id),
            ('session_id.start_at',        '>=', dt_min),
            ('session_id.start_at',        '<=', dt_max),
            ('sage_x3_sent',                '=',  False),
            ('payment_method_id.is_limit',  '=',  True),
        ])
        facli_sessions = facli_payments.mapped('session_id')

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
            ('journal_id.is_payment_sage', '!=', False),
        ])

        if not pos_sessions and not account_payments and not facli_sessions:
            return None

        # Bloquer si session encore ouverte (y compris celles uniquement
        # concernées par une FACLI en attente)
        all_sessions = pos_sessions | facli_sessions
        if all_sessions:
            open_sessions = all_sessions.filtered(lambda s: s.state != 'closed')
            if open_sessions:
                names = ', '.join(open_sessions.mapped('name'))
                raise UserError(
                    f"Sessions POS encore ouvertes ({company.name} — {target_date}) :\n"
                    f"{names}\n\nFermez toutes les sessions avant d'envoyer à SAGE X3."
                )

        # Config société
        site         = company.sage_x3_site
        journal      = company.sage_x3_journal_caisse
        sale_account = company.sage_x3_account_sale_id
        cust_account = company.sage_x3_account_customer_default_id
        caisse_acct  = company.sage_x3_account_caisse_id
        sale_tva_9   = company.sage_x3_account_sale_tva_9_id
        sale_tva_18  = company.sage_x3_account_sale_tva_18_id
        sale_airsi   = company.sage_x3_account_sale_airsi_id
        magasin      = self._get_company_code(company)
        date_yy      = target_date.strftime("%d%m%y")
        date_fr      = target_date.strftime("%d/%m/%Y")
        divers       = company.partner_devers_id.customer_id if company.partner_devers_id else ""

        for label, val in [
            ("Site SAGE X3",   site),
            ("Journal caisse", journal),
            ("Compte vente",   sale_account),
            ("Compte client",  cust_account),
            ("Compte caisse",  caisse_acct),
        ]:
            if not val:
                raise UserError(f"{label} non configuré pour {company.name}")

        # =====================================================================
        # COLLECTE PAIEMENTS POS — on track les IDs par destination
        # =====================================================================
        encai_pos_total         = 0.0
        encai_payment_ids       = []   # pos.payment IDs → ENCAI (cash sans flag)
        decai_individual_food   = []
        decai_grouped_by_compte = {}
        decai_payment_ids       = []   # pos.payment IDs → DECAI

        if pos_sessions:
            encai_pos_total = self.get_pos_lines_total_ht(pos_sessions)

        for session in pos_sessions:
            payments = self.env['pos.payment'].search([
                ('session_id', '=', session.id),
                ('sage_x3_sent', '=',  False),
            ])

            for payment in payments:
                method = payment.payment_method_id
                if not method:
                    _logger.warning("⚠️ Paiement sans méthode ignoré — session %s",
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
                            "❌ Mode '%s' ignoré : aucun compte comptable.", method.name
                        )
                        continue

                partner    = payment.partner_id
                tiers_code = (
                    partner.customer_account.strip()
                    if partner and partner.customer_account else ""
                )
                pay_date  = (
                    payment.payment_date.strftime("%d/%m/%Y")
                    if payment.payment_date else date_fr
                )
                order_ref = (
                    payment.pos_order_id.name
                    if getattr(payment, 'pos_order_id', False)
                    else (payment.name or '')
                )

                if method.is_limit:
                    # → géré dans _ligne_ecritures_is_limit (FACLI)
                    continue

                elif method.is_food:
                    if not tiers_code:
                        pay_account = cust_account
                        parent = partner.parent_id.customer_id
                        tiers_code  = parent if parent else divers
                    partner_name = partner.name if partner else ''
                    decai_individual_food.append({
                        "compte":  pay_account.code,
                        "libelle": f"CREDIT ALIMENT {partner_name} N°{order_ref}",
                        "montant": amount,
                        "tiers":   tiers_code,
                    })
                    decai_payment_ids.append(payment.id)   # ← DECAI

                elif method.is_bank_card:
                    compte = pay_account.code
                    if compte not in decai_grouped_by_compte:
                        decai_grouped_by_compte[compte] = {
                            "montant": 0.0,
                            "libelle": f"CB {method.name} DU {date_fr}",
                        }
                    decai_grouped_by_compte[compte]["montant"] += amount
                    decai_payment_ids.append(payment.id)   # ← DECAI

                elif method.is_cheque:
                    compte = pay_account.code
                    if compte not in decai_grouped_by_compte:
                        decai_grouped_by_compte[compte] = {
                            "montant": 0.0,
                            "libelle": f"CHQ {method.name} DU {date_fr}",
                        }
                    decai_grouped_by_compte[compte]["montant"] += amount
                    decai_payment_ids.append(payment.id)   # ← DECAI

                elif method.is_titre_paiement:
                    compte = pay_account.code
                    if compte not in decai_grouped_by_compte:
                        decai_grouped_by_compte[compte] = {
                            "montant": 0.0,
                            "libelle": f"PAIEMT {method.name} DU {date_fr}",
                        }
                    decai_grouped_by_compte[compte]["montant"] += amount
                    decai_payment_ids.append(payment.id)   # ← DECAI

                else:
                    # Paiement cash sans flag → ENCAI
                    encai_payment_ids.append(payment.id)   # ← ENCAI

        # =====================================================================
        # CONSTRUCTION ENCAI (facture)
        # =====================================================================
        lignes_encai = []
        total_encai  = 0.0

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
                compte = sale_airsi

            if montant > 0:
                lignes_encai.append(self._build_ligne(
                    site    = site,
                    compte  = compte.code if hasattr(compte, 'code') else compte,
                    sens    = -1,
                    montant = round(montant, 2),
                    libelle = f"TVA {taux_int}% {date_fr}",
                ))
                total_encai += montant

        for pmt in account_payments:
            if not pmt.partner_id or not pmt.partner_id.customer_id:
                _logger.warning(
                    "⚠️ Règlement %s ignoré (partenaire ou tiers manquant)", pmt.name
                )
                continue

            journal_name = pmt.journal_id.name or ''
            ref_pmt      = pmt.name or ''
            libelle_pmt  = f"REGLT {journal_name} N°{ref_pmt}/{pmt.partner_id.name}"[:50]

            customer_id = (pmt.partner_id.customer_id or "").strip()
            if customer_id.startswith(("10", "20")):
                tiers_code = divers
            else:
                tiers_code = customer_id

            lignes_encai.append(self._build_ligne(
                site    = site,
                compte  = cust_account.code,
                sens    = -1,
                montant = round(pmt.amount, 2),
                libelle = libelle_pmt,
                tiers   = tiers_code,
            ))
            total_encai += pmt.amount

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
        # =====================================================================
        lignes_decai = []
        total_decai  = 0.0

        for line in sorted(decai_individual_food,
                           key=lambda x: (x['compte'], x.get('tiers', ''))):
            lignes_decai.append(self._build_ligne(
                site    = site,
                compte  = line['compte'],
                sens    = 1,
                montant = round(line['montant'], 2),
                libelle = line['libelle'],
                tiers   = line.get('tiers', ''),
            ))
            total_decai += line['montant']

        for compte, data in sorted(decai_grouped_by_compte.items()):
            montant = data['montant']
            if montant > 0:
                lignes_decai.append(self._build_ligne(
                    site    = site,
                    compte  = compte,
                    sens    = 1,
                    montant = round(montant, 2),
                    libelle = data['libelle'],
                ))
                total_decai += montant

        if lignes_decai and total_decai > 0:
            lignes_decai.append(self._build_ligne(
                site    = site,
                compte  = caisse_acct.code,
                sens    = -1,
                montant = round(total_decai, 2),
                libelle = f"CAISSE {magasin} DU {date_fr}",
            ))

        # =====================================================================
        # ASSEMBLAGE FINAL + construction du payment_map
        #
        # payment_map = {index_ecriture: [pos.payment IDs]}
        # Permet de savoir quels paiements marquer après chaque POST réussi.
        # =====================================================================
        ecritures   = []
        payment_map = {}

        total_debit = 0.0
        total_credit = 0.0

        for l in lignes_encai:
            if l['sens'] == 1:
                total_debit += l['montant']
            else:
                total_credit += l['montant']

        total_debit = round(total_debit, 2)
        total_credit = round(total_credit, 2)

        ecart = round(total_debit - total_credit, 2)

        # ── Ajustement si déséquilibre ─────────────────────────
        if ecart != 0:
            for l in lignes_encai:
                if l['sens'] == 1:  # ligne client (débit)
                    l['montant'] = round(l['montant'] - ecart, 2)
                    break

        if lignes_encai and total_encai > 0:
            idx = len(ecritures)
            ecritures.append(self._build_ecriture(
                type_piece  = "ENCAI",
                site        = site,
                date_ddmmyy = date_yy,
                journal     = journal,
                libelle     = f"ENCAI CAISSE {magasin} DU {date_fr}",
                lignes      = lignes_encai,
            ))
            payment_map[idx] = encai_payment_ids   # cash → ENCAI

        if lignes_decai and total_decai > 0:
            idx = len(ecritures)
            ecritures.append(self._build_ecriture(
                type_piece  = "DECAI",
                site        = site,
                date_ddmmyy = date_yy,
                journal     = journal,
                libelle     = f"DECAI CAISSE {magasin} DU {date_fr}",
                lignes      = lignes_decai,
            ))
            payment_map[idx] = decai_payment_ids   # food + grouped → DECAI

        # FACLI : 1 écriture par paiement is_limit → 1 ID par index
        facli_result = self._ligne_ecritures_is_limit(facli_sessions, company)
        if facli_result and facli_result.get("ecritures"):
            for ecriture, payment_id in zip(
                facli_result["ecritures"],
                facli_result["payment_ids"],
            ):
                idx = len(ecritures)
                ecritures.append(ecriture)
                payment_map[idx] = [payment_id]    # 1 payment is_limit → 1 FACLI

        if not ecritures:
            _logger.info("ℹ️  Aucune écriture pour %s le %s", company.name, target_date)
            return None

        return {
            "ecritures":   ecritures,
            "payment_map": payment_map,
        }

    # =========================================================================
    # FACLI PAR PAIEMENT is_limit
    # =========================================================================

    def _ligne_ecritures_is_limit(self, sessions, company):
        sale_acct   = company.sage_x3_account_sale_id
        sale_tva_9  = company.sage_x3_account_sale_tva_9_id
        sale_tva_18 = company.sage_x3_account_sale_tva_18_id
        sale_airsi  = company.sage_x3_account_sale_airsi_id
        site        = company.sage_x3_site
        journal     = company.sage_x3_journal_sale
        type_piece     = "FACLI"
        type_piece_av  = "AVCLI"
        divers      = company.partner_devers_id.customer_id if company.partner_devers_id else ""

        if not sessions:
            return []

        ecritures   = []
        payment_ids = []   # même ordre que ecritures

        for session in sessions:
            payments = self.env['pos.payment'].search([
                ('session_id', '=', session.id),
                ('sage_x3_sent', '=',  False),
                ('payment_method_id.is_limit', '=', True),
            ])

            for payment in payments:
                partner        = payment.partner_id
                partner_name_c = partner.name if partner else "CLIENT"
                ticket_c       = payment.pos_order_id.pos_reference or ""

                partner_name = partner_name_c[:10]
                ticket       = ticket_c[-6:]

                receivable = self._get_receivable_account(company, partner)
                if not receivable:
                    raise UserError(
                        f"Compte client SAGE X3 ({'Int' if partner and partner.type_location == 'int' else 'Abj'}) "
                        f"non configuré pour {company.name}"
                    )

                customer_id = (partner.customer_id or "").strip() if partner else ""
                if customer_id.startswith(("10", "20")):
                    tiers_code = divers
                else:
                    tiers_code = customer_id

                pay_date = payment.payment_date.strftime("%d%m%y")   if payment.payment_date else ""
                date_fr  = payment.payment_date.strftime("%d/%m/%Y") if payment.payment_date else ""

                # =============================================================
                # CAS 1 — FACLI (paiement positif)
                # =============================================================
                if payment.amount > 0:

                    lines_with_tax, total_ht, grouped_tax = self._get_pos_order_data(
                        payment.pos_order_id.id
                    )
                    lignes = []

                    # Ligne client (débit)
                    lignes.append(self._build_ligne(
                        site    = site,
                        compte  = receivable.code,
                        sens    = 1,
                        montant = round(payment.amount, 2),
                        libelle = f"FACLI-{partner_name}-{ticket}",
                        tiers   = tiers_code,
                    ))

                    # Ligne vente HT (crédit)
                    if not lines_with_tax:
                        total_ht = round(payment.amount, 2)

                    lignes.append(self._build_ligne(
                        site    = site,
                        compte  = sale_acct.code,
                        sens    = -1,
                        montant = total_ht,
                        libelle = f"CAISSE EN COMPTE {company.name} DU {date_fr}",
                    ))

                    # Lignes TVA (crédit)
                    for taux, montant in sorted(grouped_tax.items()):
                        taux_int    = int(round(taux))
                        compte_code = self._get_tva_compte_code(taux_int, sale_tva_9, sale_tva_18, sale_airsi, company.name)
                        if not compte_code:
                            continue
                        if montant > 0:
                            lignes.append(self._build_ligne(
                                site    = site,
                                compte  = compte_code,
                                sens    = -1,
                                montant = round(montant, 2),
                                libelle = f"TVA {taux_int}% {date_fr}",
                            ))

                    # Équilibre — ajuster ligne client (sens=1)
                    self._equilibrer_lignes(lignes, sens_cible=1)

                    # Échéance SAGE X3 — uniquement sur les FACLI, pas les AVCLI.
                    date_echeance, echeances = self._build_echeances(
                        partner  = partner,
                        montant  = lignes[0]['montant'],
                        sens     = 1,
                        date_ref = payment.payment_date or fields.Date.context_today(self),
                    )

                    ecritures.append(self._build_ecriture(
                        type_piece    = type_piece,
                        site          = site,
                        date_ddmmyy   = pay_date,
                        journal       = journal,
                        libelle       = f"Mise en compte {partner_name}",
                        lignes        = lignes,
                        date_echeance = date_echeance,
                        echeances     = echeances,
                    ))
                    payment_ids.append(payment.id)

                # =============================================================
                # CAS 2 — AVCLI (paiement négatif = avoir / remboursement)
                # =============================================================
                else:

                    lines_with_tax, total_ht, grouped_tax = self._get_pos_order_data(
                        payment.pos_order_id.id
                    )
                    total_ht = abs(total_ht)   # ✅ toujours positif
                    lignes   = []

                    # Ligne client (crédit)
                    lignes.append(self._build_ligne(
                        site    = site,
                        compte  = receivable.code,
                        sens    = -1,
                        montant = round(abs(payment.amount), 2),   # ✅ positif
                        libelle = f"AVCLI-{partner_name}-{ticket}",
                        tiers   = tiers_code,
                    ))

                    # Ligne vente HT (débit)
                    if not lines_with_tax:
                        total_ht = round(abs(payment.amount), 2)

                    lignes.append(self._build_ligne(
                        site    = site,
                        compte  = sale_acct.code,
                        sens    = 1,
                        montant = total_ht,   # ✅ positif
                        libelle = f"CAISSE EN COMPTE {company.name} DU {date_fr}",
                    ))

                    # Lignes TVA (débit)
                    for taux, montant in sorted(grouped_tax.items()):
                        taux_int    = int(round(taux))
                        compte_code = self._get_tva_compte_code(taux_int, sale_tva_9, sale_tva_18, sale_airsi, company.name)
                        if not compte_code:
                            continue
                        if montant != 0:
                            lignes.append(self._build_ligne(
                                site    = site,
                                compte  = compte_code,
                                sens    = 1,
                                montant = round(abs(montant), 2),   # ✅ positif
                                libelle = f"TVA {taux_int}% {date_fr}",
                            ))

                    # Équilibre — ajuster ligne client (sens=1)
                    self._equilibrer_lignes(lignes, sens_cible=1)

                    ecritures.append(self._build_ecriture(
                        type_piece  = type_piece_av,
                        site        = site,
                        date_ddmmyy = pay_date,
                        journal     = journal,
                        libelle     = f"Avoir client {partner_name}",
                        lignes      = lignes,
                    ))
                    payment_ids.append(payment.id)

        return {
            "ecritures":   ecritures,
            "payment_ids": payment_ids,
        }

    # =========================================================================
    # HELPERS EXTRAITS — réutilisables, testables unitairement
    # =========================================================================

    def _get_pos_order_data(self, order_id):
        lines          = self.env['pos.order.line'].search([('order_id', '=', order_id)])
        total_ht       = 0.0
        lines_with_tax = lines.filtered(lambda l: l.tax_ids)
        grouped_tax    = defaultdict(float)
        for line in lines:
            price   = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            tax_res = line.tax_ids.compute_all(price, quantity=line.qty, product=line.product_id)
            # Pas de abs() ici : une ligne de remise (prix négatif) doit se
            # soustraire du total, pas s'y ajouter. Le signe final est géré
            # par l'appelant (ex: abs() appliqué une seule fois pour AVCLI).
            total_ht += tax_res['total_excluded']
            for tax_line in tax_res['taxes']:
                taux = self.env['account.tax'].browse(tax_line['id']).amount
                grouped_tax[taux] += tax_line['amount']
        grouped_tax = {t: round(m, 2) for t, m in grouped_tax.items()}
        return lines_with_tax, round(total_ht, 2), grouped_tax

    def _get_receivable_account(self, company, partner):
        """Compte client SAGE X3 pour FACLI/AVCLI selon la localité du partenaire."""
        if partner and partner.type_location == 'int':
            return company.sage_x3_account_customer_int_default_id
        return company.sage_x3_account_customer_default_id

    def _get_tva_compte_code(self, taux_int, sale_tva_9, sale_tva_18, sale_airsi, company_name):
        if taux_int == 18:
            compte_obj = sale_tva_18
        elif taux_int == 9:
            compte_obj = sale_tva_9
        else:
            compte_obj = sale_airsi
        code = compte_obj.code if compte_obj and compte_obj.code else None
        if not code:
            _logger.error("❌ Compte TVA %s%% non configuré pour %s — ligne ignorée",
                          taux_int, company_name)
        return code

    # Écart maximal (FCFA) toléré silencieusement dans _equilibrer_lignes.
    # Au-delà, on log un avertissement : un écart de cette taille trahit
    # probablement une erreur de calcul en amont, pas un simple arrondi.
    _ECART_ALERTE_SEUIL = 100

    def _equilibrer_lignes(self, lignes, sens_cible):
        total_debit  = round(sum(l['montant'] for l in lignes if l['sens'] ==  1), 2)
        total_credit = round(sum(l['montant'] for l in lignes if l['sens'] == -1), 2)
        ecart        = round(total_debit - total_credit, 2)
        if ecart != 0:
            if abs(ecart) > self._ECART_ALERTE_SEUIL:
                _logger.warning(
                    "⚠️ Écart anormal (%s FCFA) lors de l'équilibrage d'une écriture "
                    "— total_debit=%s, total_credit=%s, lignes=%s",
                    ecart, total_debit, total_credit, lignes,
                )
            for l in lignes:
                if l['sens'] == sens_cible:
                    l['montant'] = round(l['montant'] - ecart, 2)
                    break

    # =========================================================================
    # ENVOI INDIVIDUEL — anti-timeout
    # =========================================================================

    def _send_daily_to_sage_x3_api(self, accounting_data, company, target_date):
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
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

        ecritures   = accounting_data.get("ecritures", [])
        payment_map = accounting_data.get("payment_map", {})

        all_pieces   = []
        errors       = []

        # Suivi séparé ENCAI/DECAI : une FACLI/AVCLI en erreur ne doit plus
        # bloquer le marquage de la session/des règlements du jour, sinon
        # le CA et les règlements sont recalculés et renvoyés à l'identique
        # à chaque nouvelle tentative (cf. doublons ENCAI observés sur X3).
        encai_present = decai_present = False
        encai_ok      = decai_ok      = True
        encai_pieces  = encai_messages = []
        decai_pieces  = decai_messages = []

        for idx, ecriture in enumerate(ecritures):
            ecriture_type = ecriture.get("type")
            payload = {"ecritures": [ecriture]}

            _logger.info(
                "📤 Envoi écriture [%s] index=%s (%s — %s)",
                ecriture_type, idx, company.name, target_date,
            )

            try:
                response   = self._safe_post(config['accounting_url'], headers, payload)
                x3_results = self._extract_x3_results(
                    response, f"{ecriture_type}_{target_date}"
                )

                ecriture_ok   = True
                piece_numbers = []
                messages      = []

                for res in x3_results:
                    if res["piece"]:
                        piece_numbers.append(res["piece"])
                        messages.append(res["message"])
                        _logger.info(
                            "✅ [%s] Pièce SAGE X3 : %s",
                            ecriture_type, res["piece"],
                        )
                    else:
                        errors.append(
                            f"{company.name} — {target_date} [{ecriture_type}] "
                            f"{res['message']}"
                        )
                        ecriture_ok = False

                if ecriture_ok:
                    piece_str   = ", ".join(piece_numbers)
                    message_str = "\n".join(messages)

                    all_pieces.extend(piece_numbers)

                    # ✅ Marquer les pos.payment immédiatement + commit
                    # → protège contre le rollback en cas d'erreur ultérieure
                    pos_payment_ids = payment_map.get(idx, [])
                    if pos_payment_ids:
                        self._mark_pos_payments(pos_payment_ids, piece_str, message_str)
                        self.env.cr.commit()
                        _logger.info(
                            "🔒 [%s] %s pos.payment(s) marqué(s) et commité(s) — pièce %s",
                            ecriture_type, len(pos_payment_ids), piece_str,
                        )

                if ecriture_type == "ENCAI":
                    encai_present = True
                    encai_ok      = ecriture_ok
                    if ecriture_ok:
                        encai_pieces, encai_messages = piece_numbers, messages
                elif ecriture_type == "DECAI":
                    decai_present = True
                    decai_ok      = ecriture_ok
                    if ecriture_ok:
                        decai_pieces, decai_messages = piece_numbers, messages

            except Exception as e:
                errors.append(
                    f"{company.name} — {target_date} [{ecriture_type}] "
                    f"Timeout ou erreur réseau : {str(e)}"
                )
                _logger.error(
                    "❌ [%s] Échec envoi — %s", ecriture_type, str(e)
                )
                if ecriture_type == "ENCAI":
                    encai_present, encai_ok = True, False
                elif ecriture_type == "DECAI":
                    decai_present, decai_ok = True, False

        # ── Règlements hors-POS : dès que ENCAI a réussi, peu importe le ──
        # ── sort des DECAI/FACLI/AVCLI du même jour                      ──
        if encai_present and encai_ok:
            self._mark_account_payments_as_sent(
                company, target_date,
                ", ".join(encai_pieces), "\n".join(encai_messages),
            )
            self.env.cr.commit()

        # ── Session POS : dès que ENCAI et DECAI (s'ils existent) ont    ──
        # ── réussi — une FACLI bloquée ne gèle plus toute la journée     ──
        if (not encai_present or encai_ok) and (not decai_present or decai_ok):
            session_pieces   = encai_pieces + decai_pieces
            session_messages = encai_messages + decai_messages
            self._mark_pos_sessions_as_sent(
                company, target_date,
                ", ".join(session_pieces), "\n".join(session_messages),
            )
            self.env.cr.commit()

        # ── Résultat final ──────────────────────────────────────────────────────
        piece_numbers_all = ", ".join(all_pieces)

        if errors:
            _logger.warning(
                "⚠️ %s écriture(s) en erreur sur %s :\n%s",
                len(errors), target_date, "\n".join(errors),
            )
            return {"errors": errors, "pieces": piece_numbers_all}

        _logger.info("✅ SAGE X3 OK — Pièces : %s", piece_numbers_all)
        return {"errors": [], "pieces": piece_numbers_all}


    # =========================================================================
    # MARQUAGE IMMÉDIAT pos.payment (appelé après chaque écriture réussie)
    # =========================================================================

    def _mark_pos_payments(self, payment_ids, piece_numbers, message):
        """
        Marque les pos.payment comme envoyés à SAGE X3.
        Appelé juste après chaque écriture réussie pour éviter les doublons.
        Le filtre sage_x3_sent=False empêche de re-marquer un paiement déjà traité.
        """
        if not payment_ids:
            return

        payments = self.env['pos.payment'].browse(payment_ids).filtered(
            lambda p: not p.sage_x3_sent   # sécurité anti-doublon
        )

        if payments:
            payments.write({
                'sage_x3_sent':         True,
                'sage_x3_sent_date':    fields.Datetime.now(),
                'sage_x3_piece_number': piece_numbers,
            })
            _logger.info(
                "🔒 %s pos.payment(s) marqué(s) — pièce(s) : %s",
                len(payments), piece_numbers,
            )

    # =========================================================================
    # MARQUAGE FINAL — pos.session + account.payment
    # Note : pos.payment déjà marqué par _mark_pos_payments écriture par écriture.
    # Les deux méthodes ci-dessous sont indépendantes : les règlements
    # hors-POS sont liés à l'écriture ENCAI uniquement, tandis que la
    # session POS dépend à la fois d'ENCAI et de DECAI. Aucune des deux
    # n'attend le sort des FACLI/AVCLI (cf. _send_daily_to_sage_x3_api).
    # =========================================================================

    def _mark_account_payments_as_sent(self, company, target_date, piece_numbers, message):
        """Règlements clients hors POS (REGLT), inclus dans l'écriture ENCAI du jour."""
        account_payments = self.env['account.payment'].search([
            ('company_id',   '=',  company.id),
            ('payment_type', '=',  'inbound'),
            ('partner_type', '=',  'customer'),
            ('state',        '=',  'paid'),
            ('sage_x3_sent', '=',  False),
            ('date',         '=',  target_date),
            ('journal_id.is_payment_sage', '!=', False),
        ])

        if account_payments:
            account_payments.write({
                'sage_x3_sent':         True,
                'sage_x3_sent_date':    fields.Datetime.now(),
                'sage_x3_piece_number': piece_numbers,
                'message':              message,
            })
            _logger.info("✅ %s règlement(s) clients marqué(s)", len(account_payments))

    def _mark_pos_sessions_as_sent(self, company, target_date, piece_numbers, message):
        """Sessions POS du jour, une fois ENCAI et DECAI (s'ils existent) envoyés."""
        dt_min = datetime.combine(target_date, datetime.min.time())
        dt_max = datetime.combine(target_date, datetime.max.time())

        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('start_at',   '>=', dt_min),
            ('start_at',   '<=', dt_max),
        ])

        if pos_sessions:
            pos_sessions.write({
                'sage_x3_sent':         True,
                'sage_x3_sent_date':    fields.Datetime.now(),
                'sage_x3_piece_number': piece_numbers,
                'message':              message,
            })
            _logger.info("✅ %s session(s) POS marquée(s)", len(pos_sessions))

    # =========================================================================
    # PARTIE 2 — FACLI / AVCLI (factures et avoirs hors POS, sélection manuelle)
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

    # =========================================================================
    # PARTIE 3 — FACLI / AVCLI liées à des ventes (sale.order)
    # =========================================================================

    @api.model
    def _get_pending_sale_invoices(self, date_from, date_to, company_id):
        """
        Retourne les factures/avoirs clients liés à un sale.order, non encore envoyés.

        Exclut les pièces issues d'une commande POS (pos_order_ids non vide) :
        celles-ci sont déjà couvertes par le circuit POS (FACLI/AVCLI via
        _ligne_ecritures_is_limit) ; les renvoyer ici créerait un doublon
        (ex : AVCLI-O CAP SUD vs AVCLI RFAC/... pour le même remboursement).
        """
        return self.search([
            ('move_type',                      'in', ('out_invoice', 'out_refund')),
            ('state',                          '=',  'posted'),
            ('sage_x3_sent',                   '=',  False),
            ('company_id',                     '=',  company_id),
            ('invoice_date',                   '>=', date_from),
            ('invoice_date',                   '<=', date_to),
            ('invoice_line_ids.sale_line_ids', '!=', False),
            ('pos_order_ids',                  '=',  False),
        ])

    @api.model
    def _process_bulk_send_sale_invoices_to_sage_x3(self, date_from, date_to, company_ids):
        """Envoi en masse des FACLI/AVCLI liées à des ventes (sale.order)."""
        success_count = 0
        error_count   = 0
        errors        = []

        for company_id in company_ids:
            invoices = self._get_pending_sale_invoices(date_from, date_to, company_id)
            _logger.info(
                "📤 Factures ventes à envoyer — société %s : %s",
                company_id, len(invoices),
            )
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
        _logger.info(
            "📊 FACLI/AVCLI ventes — Succès: %s | Erreurs: %s",
            success_count, error_count,
        )
        return {
            'success':       success_count,
            'errors':        error_count,
            'error_details': errors,
        }

    def _send_single_invoice_to_sage_x3(self):
        """Envoie une facture (FACLI) ou un avoir (AVCLI) à SAGE X3."""
        self.ensure_one()

        if self.state != 'posted':
            raise UserError("Seules les pièces validées peuvent être envoyées.")
        if self.move_type not in ('out_invoice', 'out_refund'):
            raise UserError("Seules les factures et avoirs clients sont acceptés.")
        if self.pos_order_ids:
            # Les remboursements POS "mise en compte" (is_limit) sont envoyés en AVCLI
            # par le circuit POS (Flux 1, _ligne_ecritures_is_limit) qui marque
            # pos.payment.sage_x3_sent mais pas l'account.move. Si c'est déjà fait,
            # on synchronise le move sans renvoyer (évite le doublon).
            limit_payments = self.env['pos.payment'].search([
                ('pos_order_id',               'in', self.pos_order_ids.ids),
                ('payment_method_id.is_limit', '=',  True),
            ])
            if limit_payments and all(p.sage_x3_sent for p in limit_payments):
                self.write({
                    'sage_x3_sent':      True,
                    'sage_x3_sent_date': fields.Datetime.now(),
                })
                return
            raise UserError(
                f"{self.name} provient d'une commande POS ({', '.join(self.pos_order_ids.mapped('name'))}) "
                f"et est déjà envoyée via le circuit POS (FACLI/AVCLI). "
                f"L'envoyer ici créerait un doublon dans SAGE X3."
            )
        if not self.partner_id.customer_id:
            raise UserError(
                f"Le client {self.partner_id.name} n'a pas de code tiers SAGE X3.\n"
                f"Renseignez le champ 'Code tiers SAGE X3' sur la fiche client."
            )

        config          = self._get_sage_x3_config()
        accounting_data = self._prepare_invoice_entry()

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

        response      = self._safe_post(config['accounting_url'], headers, accounting_data)
        response_data = response.json()

        if not isinstance(response_data, list):
            raise UserError("Réponse inattendue de SAGE X3 (format non-liste)")

        x3_results       = self._extract_x3_results(response, self.name)
        errors           = []
        success_pieces   = []
        success_messages = []

        for res in x3_results:
            if res["piece"]:
                success_pieces.append(res["piece"])
                success_messages.append(res["message"])
            else:
                errors.append(res["message"])

        if errors:
            error_str = "\n".join(errors)
            self.write({
                'sage_x3_sent':      False,
                'sage_x3_sent_date': fields.Datetime.now(),
                'sage_x3_error':     error_str,
            })
            raise UserError(error_str)

        piece_numbers = ", ".join(success_pieces)
        full_message  = "\n".join(success_messages)

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
        taux = taux / 100 if taux > 1 else taux
        tva  = montant_ttc * taux / (1 + taux)
        return round(tva, 2)

    def _prepare_invoice_entry(self):
        self.ensure_one()
        company    = self.company_id
        is_refund  = (self.move_type == 'out_refund')
        type_piece = "AVCLI" if is_refund else "FACLI"

        sens_client = -1 if is_refund else  1
        sens_vente  =  1 if is_refund else -1

        receivable  = self._get_receivable_account(company, self.partner_id)
        sale_acct   = company.sage_x3_account_sale_id
        sale_tva_9  = company.sage_x3_account_sale_tva_9_id
        sale_tva_18 = company.sage_x3_account_sale_tva_18_id
        sale_airsi  = company.sage_x3_account_sale_airsi_id
        site        = company.sage_x3_site
        journal     = company.sage_x3_journal_sale

        compte_client_label = (
            "Compte client Int" if self.partner_id.type_location == 'int' else "Compte client Abj"
        )
        for label, val in [
            (compte_client_label,  receivable),
            ("Compte vente",   sale_acct),
            ("Site SAGE X3",   site),
            ("Journal vente",  journal),
            ("Compte TVA 9%",  sale_tva_9),
            ("Compte TVA 18%", sale_tva_18),
            ("Compte AIRSI",   sale_airsi),
        ]:
            if not val:
                raise UserError(f"{label} non configuré pour {company.name}")

        third_party = (self.partner_id.customer_id or "").strip()
        date_yy     = self.invoice_date.strftime("%d%m%y")
        date_fr     = self.invoice_date.strftime("%d/%m/%Y")
        magasin     = self._get_company_code(company)
        lignes      = []

        lignes.append(self._build_ligne(
            site    = site,
            compte  = receivable.code,
            sens    = sens_client,
            montant = round(self.amount_total, 2),
            libelle = f"{type_piece} {self.name}",
            tiers   = third_party,
        ))

        tax_facli = defaultdict(float)

        for line in self.line_ids:
            if not line.tax_line_id:
                continue
            taux = line.tax_line_id.amount
            amount = abs(line.balance)
            if taux == 9:
                tax_facli[sale_tva_9] += amount
            elif taux == 18:
                tax_facli[sale_tva_18] += amount
            else:
                tax_facli[sale_airsi] += amount

        tax_facli = {k: round(v, 2) for k, v in tax_facli.items()}

        if not self.amount_untaxed:
            raise UserError(f"Aucune ligne de produit valide sur {self.name}")

        if self.amount_untaxed > 0:
            lignes.append(self._build_ligne(
                site    = site,
                compte  = sale_acct.code,
                sens    = sens_vente,
                montant = round(self.amount_untaxed, 2),
                libelle = f"VENTES {date_fr}",
            ))

        for account, amount in tax_facli.items():
            if amount > 0:
                if account == sale_tva_9:
                    name    = 'TVA'
                    taux    = 9
                    libelle = f"{name} {taux}% {date_fr}"
                elif account == sale_tva_18:
                    name    = 'TVA'
                    taux    = 18
                    libelle = f"{name} {taux}% {date_fr}"
                else:
                    libelle = f"AIRSI {date_fr}"
                lignes.append(self._build_ligne(
                    site    = site,
                    compte  = account.code,
                    sens    = sens_vente,
                    montant = round(amount, 2),
                    libelle = libelle,
                ))

        self._equilibrer_lignes(lignes, sens_cible=sens_client)

        # Échéance SAGE X3 — uniquement sur les FACLI, pas les AVCLI.
        date_echeance = echeances = None
        if not is_refund:
            date_echeance, echeances = self._build_echeances(
                partner  = self.partner_id,
                montant  = lignes[0]['montant'],
                sens     = sens_client,
                date_ref = self.invoice_date,
            )

        return {
            "ecritures": [
                self._build_ecriture(
                    type_piece    = type_piece,
                    site          = site,
                    date_ddmmyy   = date_yy,
                    journal       = journal,
                    libelle       = f"{type_piece} {magasin} {self.name}",
                    lignes        = lignes,
                    date_echeance = date_echeance,
                    echeances     = echeances,
                )
            ]
        }