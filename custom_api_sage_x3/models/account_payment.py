import json
import logging

from odoo import fields, models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPaymentSageX3(models.Model):
    """
    Extension de account.payment pour l'intégration SAGE X3.

    Type de pièce généré : ENCAI (encaissement client)
    ┌──────────────────────────────────────────────────────┐
    │ DÉBIT  : Compte trésorerie (banque/caisse du journal)│
    │ CRÉDIT : Compte client 411xxx avec tiers             │
    └──────────────────────────────────────────────────────┘
    """
    _name    = 'account.payment'
    _inherit = ['account.payment', 'sage.x3.mixin']

    # =========================================================================
    # POINT D'ENTRÉE
    # =========================================================================

    def action_send_all_pending_payments_to_sage_x3(self):
        """Envoie tous les paiements clients en attente de la société courante."""
        company = self.env.company

        pending = self.search([
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state',        '=', 'paid'),
            ('sage_x3_sent', '=', False),
            ('company_id',   '=', company.id),
        ])

        if not pending:
            return {
                'type': 'ir.actions.client',
                'tag':  'display_notification',
                'params': {
                    'title':   'Information',
                    'message': 'Aucun paiement en attente à envoyer.',
                    'type':    'info',
                    'next':    {'type': 'ir.actions.client', 'tag': 'reload'},
                },
            }

        try:
            result     = self._process_bulk_send_payments_to_sage_x3(pending.ids)
            has_errors = result['errors'] > 0

            if not has_errors:
                msg   = f"{result['success']} paiement(s) envoyé(s) avec succès."
                title = '✅ Envoi terminé'
                ntype = 'success'
            else:
                details = '\n'.join(result['error_details'][:5])
                msg   = (f"{result['success']} succès, {result['errors']} erreur(s).\n"
                         f"{details}")
                title = '⚠️ Envoi terminé avec erreurs'
                ntype = 'warning'

            return {
                'type': 'ir.actions.client',
                'tag':  'display_notification',
                'params': {
                    'title':   title,
                    'message': msg,
                    'type':    ntype,
                    'sticky':  True,
                    'next':    {'type': 'ir.actions.client', 'tag': 'reload'},
                },
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag':  'display_notification',
                'params': {
                    'title':   '❌ Erreur',
                    'message': f"Erreur lors de l'envoi : {str(e)}",
                    'type':    'danger',
                    'sticky':  True,
                    'next':    {'type': 'ir.actions.client', 'tag': 'reload'},
                },
            }

    # =========================================================================
    # ENVOI EN MASSE
    # =========================================================================

    @api.model
    def _process_bulk_send_payments_to_sage_x3(self, payment_ids):
        """Envoi en masse des paiements clients (ENCAI)."""
        payments      = self.browse(payment_ids)
        success_count = 0
        error_count   = 0
        errors        = []

        _logger.info("📊 Envoi de %s paiement(s) ENCAI vers SAGE X3", len(payments))

        for idx, payment in enumerate(payments, 1):
            try:
                payment._send_payment_to_sage_x3()
                success_count += 1
                if idx % 10 == 0:
                    self.env.cr.commit()
            except Exception as e:
                error_count += 1
                errors.append(f"{payment.name}: {str(e)}")
                _logger.error("❌ Paiement %s: %s", payment.name, str(e))

        self.env.cr.commit()
        _logger.info("📊 ENCAI — Succès: %s | Erreurs: %s", success_count, error_count)
        return {'success': success_count, 'errors': error_count, 'error_details': errors}

    # =========================================================================
    # ENVOI D'UN SEUL PAIEMENT
    # =========================================================================

    def _send_payment_to_sage_x3(self):
        """
        Envoie un règlement client à SAGE X3 (type ENCAI).

        Écriture générée :
          DÉBIT  : Compte trésorerie (banque/caisse du journal de paiement)
          CRÉDIT : Compte client 411xxx avec tiers = customer_id
        """
        self.ensure_one()

        # ── Validations ───────────────────────────────────────────────────────
        if self.state != 'paid':
            raise UserError("Seuls les paiements validés peuvent être envoyés.")
        if self.payment_type != 'inbound':
            raise UserError("Seuls les paiements entrants peuvent être envoyés.")
        if self.partner_type != 'customer':
            raise UserError("Seuls les paiements clients peuvent être envoyés.")
        if not self.partner_id.customer_id:
            raise UserError(
                f"Le client {self.partner_id.name} n'a pas de code tiers SAGE X3.\n"
                f"Renseignez le champ 'Code tiers SAGE X3' sur la fiche client."
            )

        company     = self.company_id
        third_party = self.partner_id.customer_id.strip()

        # ── Comptes ───────────────────────────────────────────────────────────
        debit_account = self.journal_id.default_account_id
        if not debit_account:
            raise UserError(
                f"Compte par défaut manquant sur le journal '{self.journal_id.name}'."
            )

        credit_account = company.sage_x3_account_customer_default_id
        if not credit_account:
            raise UserError(f"Compte client SAGE X3 non configuré pour {company.name}")

        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")

        # ── Construction de l'écriture ────────────────────────────────────────
        site        = company.sage_x3_site
        journal     = company.sage_x3_journal_caisse
        date_yy     = self.date.strftime("%y%m%d")   # YYMMDD
        date_fr     = self.date.strftime("%d/%m/%Y")
        partner_lib = self.partner_id.name
        company_code = self._get_company_code(company)
        labelle     = f"Règlement {self.journal_id.name} {self.num_costomer_bank} {partner_lib}"

        lignes = [
            # DÉBIT — trésorerie
            self._build_ligne(
                site    = site,
                compte  = debit_account.code,
                sens    = 1,
                montant = self.amount,
                libelle = labelle,
            ),
            # CRÉDIT — compte client avec tiers
            self._build_ligne(
                site    = site,
                compte  = credit_account.code,
                sens    = -1,
                montant = self.amount,
                libelle = labelle,
                tiers   = third_party,
            ),
        ]

        ecriture = self._build_ecriture(
            type_piece  = "ENCAI",
            site        = site,
            date_yymmdd = date_yy,
            journal     = journal,
            libelle     = f"ENCAI {company_code} {self.name}",
            lignes      = lignes,
        )

        accounting_data = {"ecritures": [ecriture]}

        _logger.info("📦 JSON ENCAI — %s:\n%s",
                     self.name,
                     json.dumps(accounting_data, indent=2, ensure_ascii=False))

        # ── Envoi ─────────────────────────────────────────────────────────────
        config = self._get_sage_x3_config()
        token  = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

        response = self._safe_post(config['accounting_url'], headers, accounting_data)

        if response.status_code in (200, 201):
            if not response.text:
                raise UserError("Réponse vide reçue de SAGE X3")

            piece_number = self._extract_piece_number(response, self.name)

            self.write({
                'sage_x3_sent':         True,
                'sage_x3_sent_date':    fields.Datetime.now(),
                'sage_x3_piece_type':   'ENCAI',
                'sage_x3_piece_number': piece_number,
            })
            _logger.info("✅ ENCAI %s envoyé — Pièce : %s", self.name, piece_number)
        else:
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")
