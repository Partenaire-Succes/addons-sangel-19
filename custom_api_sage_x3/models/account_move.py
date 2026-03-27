import json
import logging
from datetime import datetime
from collections import defaultdict

from odoo import fields, models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMoveSageX3(models.Model):
    """
    Extension de account.move pour l'intégration SAGE X3.

    4 types de pièces gérés :
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ FACLI  Facture client         account.move out_invoice (hors POS)       │
    │ AVCLI  Avoir client           account.move out_refund  (hors POS)       │
    │ ENCAI  Encaissement caisse    Ventes POS où is_limit=False              │
    │ DECAI  Décaissement caisse    Ventes POS où is_limit=True               │
    │         ├─ is_food=True          → une ligne PAR paiement (avec tiers)  │
    │         └─ is_bank_card/cheque/  → regroupé par mode de paiement        │
    │            is_titre_paiement                                             │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    _name    = 'account.move'
    _inherit = ['account.move', 'sage.x3.mixin']

    # =========================================================================
    # POINT D'ENTRÉE — Wizard
    # =========================================================================

    def action_send_all_pending_to_sage_x3(self):
        """Ouvre le wizard de sélection de période."""
        return {
            'type':      'ir.actions.act_window',
            'name':      'Sélectionner la période',
            'res_model': 'sage.x3.send.wizard',
            'view_mode': 'form',
            'target':    'new',
        }

    # =========================================================================
    # PARTIE 1 — POS : ENCAI + DECAI (récap journalier)
    # =========================================================================

    @api.model
    def _process_bulk_send_to_sage_x3(self, date_from, date_to, company_ids):
        """
        Envoi groupé des récaps POS, par société et par jour.
        Chaque société n'envoie QUE ses propres données (isolation stricte).
        Génère jusqu'à 2 écritures par jour : ENCAI et/ou DECAI.
        """
        success_count = 0
        error_count   = 0
        errors        = []

        for company_id in company_ids:
            company = self.env['res.company'].browse(company_id)
            if not company.exists():
                _logger.error("❌ Société ID %s introuvable", company_id)
                continue

            current_date   = fields.Date.from_string(date_from)
            end_date       = fields.Date.from_string(date_to)
            company_success = 0
            company_errors  = 0

            while current_date <= end_date:
                try:
                    accounting_data = self._prepare_daily_entry(company, current_date)

                    if accounting_data and accounting_data.get('ecritures'):
                        self._send_daily_to_sage_x3_api(accounting_data, company, current_date)
                        success_count   += 1
                        company_success += 1
                        _logger.info("✅ %s — %s : envoyé (%s écriture(s))",
                                     company.name, current_date,
                                     len(accounting_data['ecritures']))
                    else:
                        _logger.info("ℹ️  %s — %s : aucune donnée", company.name, current_date)

                    self.env.cr.commit()

                except Exception as e:
                    error_count    += 1
                    company_errors += 1
                    msg = f"{company.name} — {current_date}: {str(e)}"
                    errors.append(msg)
                    _logger.error("❌ %s", msg, exc_info=True)

                current_date = fields.Date.add(current_date, days=1)

            _logger.info("📊 Société %s : %s succès / %s erreurs",
                         company.name, company_success, company_errors)

        return {'success': success_count, 'errors': error_count, 'error_details': errors}

    def _prepare_daily_entry(self, company, target_date):
        """
        Prépare les écritures journalières POS pour UNE société.

        Règles de ventilation :
        ┌──────────────────┬──────────────────────────────────────────────────┐
        │ Mode paiement    │ Type pièce  │ Regroupement                       │
        ├──────────────────┼─────────────┼────────────────────────────────────┤
        │ is_limit=False   │ ENCAI       │ Groupé par (compte, mode)          │
        │ is_limit=True    │ DECAI       │                                    │
        │   + is_food      │             │ 1 ligne par paiement (avec tiers)  │
        │   + is_bank_card │             │ Groupé par (compte, mode)          │
        │   + is_cheque    │             │ Groupé par (compte, mode)          │
        │   + is_titre_pmt │             │ Groupé par (compte, mode)          │
        └──────────────────┴─────────────┴────────────────────────────────────┘

        Retourne : {"ecritures": [...]} ou None si aucune donnée.
        """
        # Récupérer les sessions de la journée pour cette société
        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('start_at', '>=', datetime.combine(target_date, datetime.min.time())),
            ('start_at', '<=', datetime.combine(target_date, datetime.max.time())),
        ])

        if not pos_sessions:
            return None

        # Bloquer si une session est encore ouverte
        open_sessions = pos_sessions.filtered(lambda s: s.state != 'closed')
        if open_sessions:
            session_names = ', '.join(open_sessions.mapped('name'))
            raise UserError(
                f"Sessions POS encore ouvertes ({company.name} — {target_date}) :\n"
                f"{session_names}\n\n"
                f"Fermez toutes les sessions avant d'envoyer à SAGE X3."
            )

        # ── Collecte des paiements ────────────────────────────────────────────
        # ENCAI : is_limit=False, groupé par (compte, mode)
        encai_grouped = defaultdict(float)

        # DECAI is_food : non groupé, 1 ligne par paiement
        decai_food_lines = []

        # DECAI autres (bank_card, cheque, titre) : groupé par (compte, mode)
        decai_other_grouped = defaultdict(float)

        for session in pos_sessions:
            payments = self.env['pos.payment'].search([
                ('session_id', '=', session.id),
                ('sage_x3_sent', '=', False),
            ])

            for payment in payments:
                method = payment.payment_method_id
                if not method:
                    _logger.warning("⚠️ Paiement sans méthode — session %s", session.name)
                    continue

                amount = abs(payment.amount)
                if amount == 0:
                    continue

                debit_account = method.journal_id.default_account_id
                if not debit_account:
                    _logger.warning("⚠️ Compte débit manquant pour '%s'", method.name)
                    if method.is_limit:
                        debit_account = company.sage_x3_account_customer_default_id
                        if not debit_account:
                            _logger.error("❌ Compte client par défaut manquant (%s)", company.name)
                            continue
                    else:
                        continue

                if not method.is_limit:
                    # ── ENCAI : regroupé
                    encai_grouped[(debit_account.code, method.name)] += amount

                else:
                    # ── DECAI : ventilation selon le flag du mode de paiement
                    if method.is_food:
                        # Food → individuel, avec tiers
                        partner    = payment.partner_id
                        tiers_code = (
                            partner.customer_id.strip()
                            if partner and partner.customer_id
                            else ""
                        )
                        decai_food_lines.append({
                            "compte":  debit_account.code,
                            "libelle": (
                                f"{method.name} du "
                                f"{payment.payment_date.strftime('%d/%m/%Y')}"
                            ),
                            "montant": amount,
                            "tiers":   tiers_code,
                        })
                    else:
                        # bank_card / cheque / titre_paiement → groupé par mode
                        decai_other_grouped[(debit_account.code, method.name)] += amount

        # ── Construction des écritures ────────────────────────────────────────
        ecritures  = []
        site       = company.sage_x3_site
        journal    = company.sage_x3_journal_sale
        date_yy    = target_date.strftime("%y%m%d")   # format YYMMDD (ex: "260323")
        date_fr    = target_date.strftime("%d/%m/%Y")

        if not site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")
        if not journal:
            raise UserError(f"Journal vente SAGE X3 non configuré pour {company.name}")

        sale_account = company.sage_x3_account_sale_id
        if not sale_account:
            raise UserError(f"Compte de vente SAGE X3 non configuré pour {company.name}")

        # ── ENCAI ─────────────────────────────────────────────────────────────
        if encai_grouped:
            lignes_encai = []
            total_encai  = 0.0

            for (compte, method_name), amount in sorted(encai_grouped.items()):
                if amount > 0:
                    lignes_encai.append(self._build_ligne(
                        site    = site,
                        compte  = compte,
                        sens    = 1,
                        montant = amount,
                        libelle = f"{method_name} du {date_fr}",
                    ))
                    total_encai += amount

            # Ligne crédit globale (compte de vente)
            lignes_encai.append(self._build_ligne(
                site    = site,
                compte  = sale_account.code,
                sens    = -1,
                montant = total_encai,
                libelle = f"Ventes {date_fr}",
            ))

            ecritures.append(self._build_ecriture(
                type_piece  = "ENCAI",
                site        = site,
                date_yymmdd = date_yy,
                journal     = journal,
                libelle     = f"Ventes caisse {date_fr}",
                lignes      = lignes_encai,
            ))

        # ── DECAI ─────────────────────────────────────────────────────────────
        if decai_food_lines or decai_other_grouped:
            lignes_decai = []
            total_decai  = 0.0

            # Food : individuel, trié par (compte, tiers)
            for line in sorted(decai_food_lines,
                                key=lambda x: (x['compte'], x.get('tiers', ''))):
                lignes_decai.append(self._build_ligne(
                    site    = site,
                    compte  = line['compte'],
                    sens    = 1,
                    montant = line['montant'],
                    libelle = line['libelle'],
                    tiers   = line['tiers'],
                ))
                total_decai += line['montant']

            # bank_card / cheque / titre : groupé
            for (compte, method_name), amount in sorted(decai_other_grouped.items()):
                if amount > 0:
                    lignes_decai.append(self._build_ligne(
                        site    = site,
                        compte  = compte,
                        sens    = 1,
                        montant = amount,
                        libelle = f"{method_name} du {date_fr}",
                    ))
                    total_decai += amount

            # Ligne crédit globale DECAI
            lignes_decai.append(self._build_ligne(
                site    = site,
                compte  = sale_account.code,
                sens    = -1,
                montant = total_decai,
                libelle = f"Ventes crédit {date_fr}",
            ))

            ecritures.append(self._build_ecriture(
                type_piece  = "DECAI",
                site        = site,
                date_yymmdd = date_yy,
                journal     = journal,
                libelle     = f"Ventes crédit {date_fr}",
                lignes      = lignes_decai,
            ))

        if not ecritures:
            _logger.info("ℹ️  Aucun paiement valide pour %s le %s", company.name, target_date)
            return None

        return {"ecritures": ecritures}

    def _send_daily_to_sage_x3_api(self, accounting_data, company, target_date):
        """Envoie les écritures journalières POS (ENCAI + DECAI) à SAGE X3."""
        config = self._get_sage_x3_config()
        _logger.info("📦 JSON POS (%s — %s):\n%s",
                     company.name, target_date,
                     json.dumps(accounting_data, indent=2, ensure_ascii=False))

        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

        response = self._safe_post(config['accounting_url'], headers, accounting_data)

        if response.status_code in (200, 201):
            piece_number = self._extract_piece_number(response, f"POS_{target_date}")
            _logger.info("✅ SAGE X3 OK — Pièce : %s", piece_number)
            self._mark_pos_payments_as_sent(company, target_date, piece_number)
        else:
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")

    def _mark_pos_payments_as_sent(self, company, target_date, piece_number):
        """
        Marque les paiements POS de la journée comme envoyés.
        Note : la pièce SAGE X3 est un récap journalier — les account.move POS
               individuels ne sont intentionnellement pas marqués ici.
        """
        pos_sessions = self.env['pos.session'].search([
            ('company_id', '=', company.id),
            ('start_at', '>=', datetime.combine(target_date, datetime.min.time())),
            ('start_at', '<=', datetime.combine(target_date, datetime.max.time())),
        ])

        pos_payments = self.env['pos.payment'].search([
            ('session_id',    'in', pos_sessions.ids),
            ('sage_x3_sent', '=',  False),
        ])

        if pos_payments:
            pos_payments.write({
                'sage_x3_sent':         True,
                'sage_x3_sent_date':    fields.Datetime.now(),
                'sage_x3_piece_number': piece_number,
            })
            _logger.info("✅ %s paiement(s) POS marqués envoyés", len(pos_payments))

    # =========================================================================
    # PARTIE 2 — FACLI / AVCLI (factures et avoirs classiques hors POS)
    # =========================================================================

    @api.model
    def _process_bulk_send_classic_invoices_to_sage_x3(self, invoice_ids):
        """Envoi en masse des factures et avoirs classiques (hors POS)."""
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
                _logger.error("❌ Facture %s: %s", invoice.name, str(e))

        self.env.cr.commit()
        _logger.info("📊 Factures/Avoirs — Succès: %s | Erreurs: %s",
                     success_count, error_count)
        return {'success': success_count, 'errors': error_count, 'error_details': errors}

    def _send_single_invoice_to_sage_x3(self):
        """
        Envoie une facture (FACLI) ou un avoir (AVCLI) à SAGE X3.
        Le type est déterminé automatiquement depuis move_type.
        """
        self.ensure_one()

        if self.state != 'posted':
            raise UserError("Seules les pièces validées peuvent être envoyées.")
        if self.move_type not in ('out_invoice', 'out_refund'):
            raise UserError("Seules les factures et avoirs clients peuvent être envoyés.")
        if not self.partner_id.customer_id:
            raise UserError(
                f"Le client {self.partner_id.name} n'a pas de code tiers SAGE X3.\n"
                f"Renseignez le champ 'Code tiers SAGE X3' sur la fiche client."
            )

        config          = self._get_sage_x3_config()
        accounting_data = self._prepare_invoice_entry(self)

        if not accounting_data:
            raise UserError("Impossible de préparer les données.")

        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

        _logger.info("📦 JSON %s — %s:\n%s",
                     accounting_data['ecritures'][0]['type'], self.name,
                     json.dumps(accounting_data, indent=2, ensure_ascii=False))

        response = self._safe_post(config['accounting_url'], headers, accounting_data)

        if response.status_code in (200, 201):
            if not response.text:
                raise UserError("Réponse vide reçue de SAGE X3")

            type_piece   = accounting_data['ecritures'][0]['type']
            piece_number = self._extract_piece_number(response, self.name)

            self.write({
                'sage_x3_sent':         True,
                'sage_x3_sent_date':    fields.Datetime.now(),
                'sage_x3_piece_type':   type_piece,
                'sage_x3_piece_number': piece_number,
            })
            _logger.info("✅ %s %s envoyé — Pièce : %s", type_piece, self.name, piece_number)
        else:
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")

    def _prepare_invoice_entry(self, invoice):
        """
        Prépare l'écriture pour une facture (FACLI) ou un avoir (AVCLI).

        FACLI — Facture client :
          DÉBIT  compte client (411xxx)  tiers=customer_id  sens=1
          CRÉDIT compte vente unique     (mapping volontaire) sens=-1

        AVCLI — Avoir client :
          CRÉDIT compte client (411xxx)  tiers=customer_id  sens=-1
          DÉBIT  compte vente            sens=1
          (les sens sont inversés par rapport à la facture)
        """
        company     = invoice.company_id
        is_refund   = (invoice.move_type == 'out_refund')
        type_piece  = "AVCLI" if is_refund else "FACLI"

        # Sens : facture → client=1/vente=-1  |  avoir → client=-1/vente=1
        sens_client = -1 if is_refund else 1
        sens_vente  = 1  if is_refund else -1

        # Vérifications configuration
        receivable_account = company.sage_x3_account_customer_default_id
        if not receivable_account:
            raise UserError(f"Compte client SAGE X3 non configuré pour {company.name}")

        credit_account = company.sage_x3_account_sale_id
        if not credit_account:
            raise UserError(f"Compte vente SAGE X3 non configuré pour {company.name}")

        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")
        if not company.sage_x3_journal_sale:
            raise UserError(f"Journal vente SAGE X3 non configuré pour {company.name}")

        site        = company.sage_x3_site
        third_party = invoice.partner_id.customer_id.strip()
        date_yy     = invoice.invoice_date.strftime("%y%m%d")
        date_fr     = invoice.invoice_date.strftime("%d/%m/%Y")
        lignes      = []

        # ── 1. Ligne client (débit pour FACLI, crédit pour AVCLI) ────────────
        lignes.append(self._build_ligne(
            site    = site,
            compte  = receivable_account.code,
            sens    = sens_client,
            montant = invoice.amount_total,
            libelle = f"{type_piece} {invoice.name}",
            tiers   = third_party,
        ))

        # ── 2. Lignes vente par compte produit Odoo ───────────────────────────
        # Mapping volontaire : toutes les lignes vont sur credit_account
        # (un compte unique SAGE X3), mais on garde le détail par compte Odoo
        product_totals = defaultdict(float)
        for line in invoice.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note'):
                continue
            if not line.account_id or line.price_total == 0:
                continue
            product_totals[line.account_id.code] += line.price_total

        if not product_totals:
            raise UserError(f"Aucune ligne de produit valide sur {invoice.name}")

        for _odoo_code, amount in sorted(product_totals.items()):
            if amount > 0:
                lignes.append(self._build_ligne(
                    site    = site,
                    compte  = credit_account.code,   # mapping unique volontaire
                    sens    = sens_vente,
                    montant = amount,
                    libelle = f"Ventes {date_fr}",
                ))

        # ── 3. Construction de l'écriture ─────────────────────────────────────
        company_code = self._get_company_code(company)
        ecriture = self._build_ecriture(
            type_piece  = type_piece,
            site        = site,
            date_yymmdd = date_yy,
            journal     = company.sage_x3_journal_sale,
            libelle     = f"{type_piece} {company_code} {invoice.name}",
            lignes      = lignes,
        )

        return {"ecritures": [ecriture]}