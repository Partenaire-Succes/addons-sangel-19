import time
import gc
import logging

import requests
from dateutil import parser

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MAX_RETRIES = 3
PAGE_SIZE   = 100
COMMIT_STEP = 20
MAX_PAGES   = 1000
TIMEOUT     = 30
MAX_DURATION = 300  # 5 minutes


class ResPartnerImport(models.Model):
    _name  = 'res.partner'
    _inherit = ['res.partner', 'sage.x3.mixin']

    # =========================================================================
    # POINT D'ENTRÉE
    # =========================================================================

    def import_contacts(self):
        return self.action_import_contacts_external_source()

    def action_import_contacts_external_source(self):
        """
        Importe les contacts/clients depuis l'API SAGE X3.
        • Pagination automatique
        • Commit tous les COMMIT_STEP contacts
        • Rollback par contact en cas d'erreur isolée
        • Arrêt automatique après MAX_DURATION secondes
        """
        try:
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec de l'authentification SAGE X3")

            config = self._get_sage_x3_config()
            if isinstance(config, dict):
                base_url = config.get('base_url') or config.get(0)
            else:
                base_url = config[0]
            customers_url  = f"{base_url}/api/Customers"
            headers        = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

            # -----------------------------------------------------------------
            # 1. Récupération paginée
            # -----------------------------------------------------------------
            all_customers = []
            page          = 1
            start_time    = time.time()

            _logger.info("🚀 Démarrage de l'importation des contacts...")

            while page <= MAX_PAGES:
                if time.time() - start_time > MAX_DURATION:
                    _logger.warning("⏱️ Import interrompu : durée maximale atteinte (%ss)", MAX_DURATION)
                    break

                params   = {"pageNumber": page, "pageSize": PAGE_SIZE}
                response = self._safe_get(customers_url, headers, params)
                data     = response.json()
                items    = data.get("items", [])
                all_customers.extend(items)
                _logger.info("📦 Page %s récupérée (%s contacts)", page, len(items))

                if not data.get("hasNextPage", False):
                    break
                page += 1

            _logger.info("✅ Récupération terminée : %s contacts à traiter", len(all_customers))

            # -----------------------------------------------------------------
            # 2. Traitement contact par contact
            # -----------------------------------------------------------------
            created = updated = skipped = errors = 0
            # On garde une référence stable au modèle pour les cas de rollback
            partner_model = self.env['res.partner']

            for idx, customer in enumerate(all_customers, start=1):
                try:
                    vals = partner_model.prepare_contact_values(customer)

                    if not vals.get("customer_id"):
                        _logger.warning("⚠️ Contact ignoré sans code client : %s", vals.get("name"))
                        skipped += 1
                        continue
                    if not vals.get("name"):
                        _logger.warning("⚠️ Contact ignoré sans nom : %s", vals.get("customer_id"))
                        skipped += 1
                        continue

                    existing = partner_model.search(
                        [("customer_id", "=", vals["customer_id"])], limit=1
                    )

                    if existing:
                        existing.write(vals)
                        existing.name = vals["name"]  # Forcer la mise à jour du nom dans le cache d'Odoo
                        _logger.info("🔄 Mis à jour : %s (%s)", existing.name, existing.customer_id)
                        existing.write({'customer_account': vals.get("customer_account", existing.customer_account)})
                        updated += 1
                    else:
                        contact = partner_model.create(vals)
                        _logger.info("✅ Créé : %s (%s)", contact.name, contact.customer_id)
                        created += 1

                    if idx % COMMIT_STEP == 0:
                        self.env.cr.commit()
                        gc.collect()
                        _logger.info("💾 Commit après %s contacts", idx)

                except Exception as e:
                    errors += 1
                    _logger.exception("❌ Erreur contact %s : %s",
                                      customer.get("bpcnuM_0"), str(e))
                    # Rollback de la transaction courante pour continuer proprement
                    try:
                        if not self.env.cr.closed:
                            self.env.cr.rollback()
                            self.env.invalidate_all()
                        else:
                            _logger.warning("⚠️ Curseur déjà fermé, rollback impossible")
                        # Rafraîchir la référence au modèle après rollback
                        partner_model = self.env['res.partner']
                    except Exception as rollback_err:
                        _logger.warning("⚠️ Rollback échoué : %s", str(rollback_err))

            # Commit final
            self.env.cr.commit()

            _logger.info("=" * 50)
            _logger.info("=== RÉSUMÉ IMPORTATION CONTACTS ===")
            _logger.info("✅ Créés       : %s", created)
            _logger.info("🔄 Mis à jour  : %s", updated)
            _logger.info("⏩ Ignorés     : %s", skipped)
            _logger.info("❌ Erreurs     : %s", errors)
            _logger.info("📊 Total traité: %s", created + updated + skipped)
            _logger.info("=" * 50)

        except Exception as e:
            _logger.exception("🚨 Échec global de l'importation des contacts : %s", str(e))
            raise UserError("L'importation des contacts a échoué.")

    # =========================================================================
    # HTTP — GET PAGINÉ (utilise le mixin pour l'auth, implémente son propre GET)
    # =========================================================================

    def _safe_get(self, url, headers, params, timeout=TIMEOUT):
        """GET avec retry et timeout."""
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ HTTP inattendu (tentative %s) : %s", attempt, response.status_code)
                last_exc = Exception(f"HTTP {response.status_code}")
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s) : %s", attempt, str(e))
                last_exc = e
            time.sleep(5)
        raise UserError(f"Échec de récupération des données après {MAX_RETRIES} tentatives : {last_exc}")

    # =========================================================================
    # OUTILS DE CONVERSION
    # =========================================================================

    def _safe_float(self, value, default=0.0):
        if not value:
            return default
        try:
            return float(str(value).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            return default

    def _safe_string(self, value, default=""):
        if not value or str(value).strip() == "":
            return default
        return str(value).strip()

    def _safe_datetime(self, value):
        if not value:
            return False
        try:
            return parser.parse(value)
        except Exception as e:
            _logger.warning("⚠️ Date invalide : %s (%s)", value, str(e))
            return False

    # =========================================================================
    # PRÉPARATION DES VALEURS
    # =========================================================================

    def prepare_contact_values(self, customer):
        """Construit le dict de valeurs pour create/write d'un res.partner."""
        customer_code = self._safe_string(customer.get("bpcnuM_0"))
        if not customer_code:
            raise ValueError("Code client manquant")

        name        = self._safe_string(customer.get("bpcnaM_0"))
        # if not name:
        #     raise ValueError(f"Nom manquant pour client {customer_code}")
        
        is_company  = bool(self._safe_string(customer.get("crN_0")))
        vat_regime  = self._safe_string(customer.get("vacbpR_0"))
        is_airsi    = (vat_regime == "AIRSI")
        credit_limit = self._safe_float(customer.get("ostauZ_0"))
        is_limit    = (credit_limit > 0)

        vals = {
            "name":               name,
            "customer_id":        customer_code,
            "customer_account":   self._safe_string(customer.get("bprnuM_SALARIE")),
            "is_company":         is_company,
            "customer_rank":      1,
            "street":             self._safe_string(customer.get("bpaadD_0")),
            "city":               self._safe_string(customer.get("ctY_0")),
            "phone":              self._safe_string(customer.get("teL_0")),
            "vat":                self._safe_string(customer.get("naF_0")),
            "company_registry":   self._safe_string(customer.get("crN_0")),
            "active":             True,
            "is_airsi_eligible":  is_airsi,
            "is_limit":           is_limit,
            "amount_credit_limit": credit_limit,
            "code_family":        self._safe_string(customer.get("tsccoD_0")),
        }

        category_id = self._get_category_id(customer.get("bccgcoD_0"))
        if category_id:
            vals["category_id"] = [(4, category_id)]

        currency_id = self._get_currency_id(customer.get("cuR_0"))
        if currency_id:
            vals["currency_id"] = currency_id

        primary_resp = self._get_responsible_id(customer.get("reP_0"))
        if primary_resp:
            vals["primary_responsible_id"] = primary_resp

        secondary_resp = self._get_responsible_id(customer.get("reP_1"))
        if secondary_resp:
            vals["secondary_responsible_id"] = secondary_resp

        payment_term = self._get_property_payment_term_id(customer.get("ptE_0"))
        if payment_term:
            vals["property_payment_term_id"] = payment_term

        create_date = self._safe_datetime(customer.get("credattiM_0"))
        if create_date:
            vals["create_date_sage"] = create_date

        update_date = self._safe_datetime(customer.get("upddattiM_0"))
        if update_date:
            vals["update_date_sage"] = update_date

        return vals

    # =========================================================================
    # GETTERS Many2one / Many2many
    # =========================================================================

    def _get_category_id(self, name):
        if not name:
            return False
        try:
            rec = self.env["res.partner.category"].search([("name", "ilike", name)], limit=1)
            if rec:
                return rec.id
            new_rec = self.env["res.partner.category"].create({"name": name})
            _logger.info("➕ Catégorie créée : %s", name)
            return new_rec.id
        except Exception as e:
            _logger.warning("⚠️ Erreur catégorie '%s' : %s", name, str(e))
            return False

    def _get_currency_id(self, name):
        if not name:
            return False
        try:
            rec = self.env["res.currency"].search([("name", "=", name)], limit=1)
            if rec:
                return rec.id
            _logger.warning("⚠️ Devise introuvable : %s", name)
            return False
        except Exception as e:
            _logger.warning("⚠️ Erreur devise '%s' : %s", name, str(e))
            return False

    def _get_responsible_id(self, name):
        if not name:
            return False
        try:
            rec = self.env["res.users"].search([("name", "ilike", name)], limit=1)
            if rec:
                return rec.id
            _logger.debug("ℹ️ Utilisateur introuvable : %s", name)
            return False
        except Exception as e:
            _logger.warning("⚠️ Erreur utilisateur '%s' : %s", name, str(e))
            return False

    def _get_property_payment_term_id(self, name):
        if not name:
            return False
        try:
            rec = self.env["account.payment.term"].search([("name", "ilike", name)], limit=1)
            if rec:
                return rec.id
            new_rec = self.env["account.payment.term"].create({
                "name": name,
                "note": f"Condition de paiement: {name}",
            })
            _logger.info("➕ Condition de paiement créée : %s", name)
            return new_rec.id
        except Exception as e:
            _logger.warning("⚠️ Erreur condition paiement '%s' : %s", name, str(e))
            return False
