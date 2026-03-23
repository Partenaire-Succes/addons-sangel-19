import logging
import json

from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPaymentSageX3(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment', 'sage.x3.mixin']

    # =========================================================================
    # PAIEMENTS CLIENTS (REGCLI)
    # =========================================================================

    def action_send_all_pending_payments_to_sage_x3(self):
        """
        Envoie tous les paiements clients non envoyés de la société courante.
        Envoi direct, sans wizard.
        """
        company = self.env.company

        pending_payments = self.search([
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('state', '=', 'paid'),
            ('sage_x3_sent', '=', False),
            ('company_id', '=', company.id),
        ])

        if not pending_payments:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Information',
                    'message': 'Aucun paiement à envoyer.',
                    'type': 'info',
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }

        try:
            result = self._process_bulk_send_payments_to_sage_x3(pending_payments.ids)

            if result['errors'] == 0:
                msg = f"{result['success']} paiement(s) envoyé(s) avec succès."
                notif_type = 'success'
                title = '✅ Envoi terminé'
            else:
                details = '\n'.join(result['error_details'][:5])
                msg = (
                    f"{result['success']} succès, {result['errors']} erreur(s).\n{details}"
                )
                notif_type = 'warning'
                title = '⚠️ Envoi terminé avec erreurs'

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': title,
                    'message': msg,
                    'type': notif_type,
                    'sticky': True,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '❌ Erreur',
                    'message': f"Erreur lors de l'envoi : {str(e)}",
                    'type': 'danger',
                    'sticky': True,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }

    @api.model
    def _process_bulk_send_payments_to_sage_x3(self, payment_ids):
        """Envoi en masse des paiements clients."""
        payments = self.browse(payment_ids)
        success_count = 0
        error_count = 0
        errors = []

        _logger.info("📊 Envoi de %s paiement(s) vers SAGE X3", len(payments))

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
        _logger.info("📊 Paiements — Succès: %s | Erreurs: %s", success_count, error_count)

        return {'success': success_count, 'errors': error_count, 'error_details': errors}

    def _send_payment_to_sage_x3(self):
        """
        Envoie un règlement client à SAGE X3 (type REGCLI).

        Structure :
        - DÉBIT  : Compte de trésorerie (banque/caisse selon le journal)
        - CRÉDIT : Compte client (411xxx) avec thirdParty
        """
        self.ensure_one()

        # --- Validations ---
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

        company = self.company_id
        third_party = self.partner_id.customer_id.strip()
        lines = []

        # --- 1. DÉBIT trésorerie ---
        debit_account = self.journal_id.default_account_id
        if not debit_account:
            raise UserError(
                f"Compte par défaut manquant sur le journal '{self.journal_id.name}'."
            )

        lines.append({
            "account": debit_account.code,
            "label": f"Règlement {self.partner_id.name}",
            "sense": 1,
            "amount": self.amount,
            "thirdParty": "",
        })

        # --- 2. CRÉDIT client ---
        credit_account = company.sage_x3_account_customer_default_id
        if not credit_account:
            raise UserError(
                f"Compte client SAGE X3 non configuré pour {company.name}.\n"
                f"Paramètres > Sociétés > {company.name}"
            )

        lines.append({
            "account": credit_account.code,
            "label": f"Règlement {self.partner_id.name}",
            "sense": -1,
            "amount": self.amount,
            "thirdParty": third_party,
        })

        # --- 3. Pièce comptable ---
        if not company.sage_x3_site:
            raise UserError(f"Site SAGE X3 non configuré pour {company.name}")

        company_code = self._get_company_code(company)

        piece = {
            "type": "REGCLI",
            "numero": "",
            "site": company.sage_x3_site,
            "date": self.date.strftime("%Y-%m-%d"),
            "journal": self.journal_id.name,
            "reference": f"REGCLI_{company_code}_{self.name.replace('/', '_')}",
            "devise": "XOF",
            "transaction": "STDCO",
        }

        accounting_data = {"entries": [{"piece": piece, "lines": lines}]}

        _logger.info("📦 Données JSON REGCLI — %s:", self.name)
        _logger.info(json.dumps(accounting_data, indent=2, ensure_ascii=False))

        # --- 4. Envoi ---
        config = self._get_sage_x3_config()
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
                'sage_x3_piece_type': 'REGCLI',
                'sage_x3_piece_number': piece_number,
            })
            _logger.info("✅ Paiement %s envoyé — Pièce : %s", self.name, piece_number)
        else:
            raise UserError(f"Erreur HTTP {response.status_code}: {response.text}")

    # =========================================================================
    # HELPER COMMUN
    # =========================================================================

    def _extract_piece_number(self, response, fallback_reference):
        """
        Extrait le numéro de pièce de la réponse SAGE X3.
        Format : G;REGCLI;;SIEGE;110226;VTE;REGCLI_REF;XOF;STDCO
        """
        try:
            first_line = response.text.strip().splitlines()[0]
            parts = first_line.split(";")
            if len(parts) >= 7 and parts[6]:
                return parts[6]
        except Exception:
            _logger.warning("⚠️ Impossible de lire le numéro de pièce dans la réponse SAGE X3")
        return fallback_reference
