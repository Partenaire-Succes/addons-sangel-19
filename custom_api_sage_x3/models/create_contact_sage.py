import requests
import logging as logger
from odoo import fields, models, api
from odoo.exceptions import UserError
from dateutil import parser
import time
import gc

_logger = logger.getLogger(__name__)

BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
CUSTOMERS_URL = f"{BASE_URL}/api/Customers"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

MAX_RETRIES = 3
PAGE_SIZE = 100
COMMIT_STEP = 20
MAX_PAGES = 1000
TIMEOUT = 30


class ResPartnerImport(models.Model):
    _inherit = "res.partner"

    def import_contacts_job(self):
        """Méthode pour lancer l'import via queue job si nécessaire"""
        self.action_import_from_external_source()

    def safe_get(self, url, headers, params, timeout=TIMEOUT):
        """Appel GET avec retry et timeout"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ Statut HTTP inattendu (tentative %s) : %s", attempt, response.status_code)
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s) : %s", attempt, str(e))
            time.sleep(5)
        raise UserError("Échec de récupération des données après plusieurs tentatives.")

    def action_import_from_external_source(self):
        """Importation des contacts/clients depuis l'API SAGE X3 avec gestion d'erreurs et commits réguliers."""
        try:
            # Authentification
            auth_data = {"username": USERNAME, "password": PASSWORD}
            response = requests.post(AUTH_URL, json=auth_data, timeout=15)
            if response.status_code not in (200, 201):
                raise UserError(f"Erreur d'authentification : {response.text}")

            token = response.json().get("token")
            if not token:
                raise UserError("Token d'authentification manquant dans la réponse.")

            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            all_customers = []
            page = 1
            start_time = time.time()

            # Récupération des données paginées
            _logger.info("🚀 Démarrage de l'importation des contacts...")
            while page <= MAX_PAGES:
                if time.time() - start_time > 300:
                    _logger.warning("⏱️ Import interrompu : durée maximale atteinte (5 minutes)")
                    break

                params = {"pageNumber": page, "pageSize": PAGE_SIZE}
                response = self.safe_get(CUSTOMERS_URL, headers, params)
                data = response.json()
                customers = data.get("items", [])
                all_customers.extend(customers)
                _logger.info("📦 Page %s récupérée (%s contacts)", page, len(customers))

                if not data.get("hasNextPage", False):
                    break
                page += 1

            _logger.info("✅ Récupération terminée : %s contacts à traiter", len(all_customers))

            created, updated, skipped, errors = 0, 0, 0, 0

            # Traitement des contacts
            for idx, customer in enumerate(all_customers, start=1):
                try:
                    vals = self.prepare_contact_values(customer)
                    
                    # Vérification du code client (customer_id)
                    if not vals.get("customer_id"):
                        _logger.warning("⚠️ Contact ignoré sans code client : %s", vals.get("name"))
                        skipped += 1
                        continue

                    # Recherche du contact existant par customer_id
                    existing = self.search([("customer_id", "=", vals["customer_id"])], limit=1)

                    if existing:
                        # Mise à jour du contact existant
                        existing.write(vals)
                        _logger.info("🔄 Contact mis à jour : %s (%s)", existing.name, existing.customer_id)
                        updated += 1
                    else:
                        # Création d'un nouveau contact
                        contact = self.create(vals)
                        created += 1
                        _logger.info("✅ Contact créé : %s (%s)", contact.name, contact.customer_id)

                    # Commit périodique
                    if idx % COMMIT_STEP == 0:
                        self.env.cr.commit()
                        gc.collect()
                        _logger.info("💾 Commit effectué après %s contacts", idx)

                except Exception as e:
                    errors += 1
                    _logger.exception("❌ Erreur contact %s : %s", customer.get("bpcnuM_0"), str(e))
                    try:
                        if not self.env.cr.closed:
                            self.env.cr.rollback()
                            self.env.invalidate_all()
                        else:
                            _logger.warning("⚠️ Curseur déjà fermé, impossible de rollback")
                        # Recréer un environnement propre pour continuer
                        self = self.env['res.partner'].sudo()
                    except Exception as rollback_error:
                        _logger.warning("⚠️ Rollback échoué : %s", str(rollback_error))

            # Commit final
            self.env.cr.commit()
            
            # Résumé de l'importation
            _logger.info("=" * 50)
            _logger.info("=== RÉSUMÉ IMPORTATION CONTACTS ===")
            _logger.info("=" * 50)
            _logger.info("✅ Créés       : %s", created)
            _logger.info("🔄 Mis à jour  : %s", updated)
            _logger.info("⏩ Ignorés     : %s", skipped)
            _logger.info("❌ Erreurs     : %s", errors)
            _logger.info("📊 Total traité: %s", created + updated + skipped)
            _logger.info("=" * 50)

        except Exception as e:
            _logger.exception("🚨 Échec global de l'importation des contacts : %s", str(e))
            raise UserError("L'importation des contacts a échoué.")

    # ----------------------------------------------------------
    # OUTILS
    # ----------------------------------------------------------
    def _safe_float(self, value, default=0.0):
        """Convertit une valeur en float de manière sécurisée"""
        if not value:
            return default
        try:
            return float(str(value).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            return default

    def _safe_string(self, value, default=""):
        """Retourne une chaîne sécurisée"""
        if not value or str(value).strip() == "":
            return default
        return str(value).strip()

    def _safe_datetime(self, value):
        """Convertit une date ISO 8601 en format Odoo"""
        if not value:
            return False
        try:
            return parser.parse(value)
        except Exception as e:
            _logger.warning("⚠️ Format de date invalide : %s (%s)", value, str(e))
            return False

    def prepare_contact_values(self, customer):
        """Prépare le dictionnaire de valeurs contact pour la création/mise à jour."""
        
        # Code client (référence obligatoire)
        customer_code = self._safe_string(customer.get("bpcnuM_0"))
        if not customer_code:
            raise ValueError("Code client manquant")

        # Nom du contact
        name = self._safe_string(customer.get("bprnaM_0"), "Contact sans nom")
        
        # Déterminer le type de contact (company ou person)
        is_company = bool(self._safe_string(customer.get("crN_0")))  # Si SIRET existe
        
        # Vérification AIRSI
        vat_regime = self._safe_string(customer.get("vacbpR_0"))
        is_airsi = (vat_regime == "AIRSI")
        
        # Vérification encours autorisé
        credit_limit = self._safe_float(customer.get("ostauZ_0"))
        is_limit = (credit_limit > 0)
        
        # Construction du dictionnaire de valeurs
        vals = {
            "name": name,
            "customer_id": customer_code,
            "is_company": is_company,
            "customer_rank": 1,  # Marquer comme client
            "street": self._safe_string(customer.get("bpaadD_0")),
            "city": self._safe_string(customer.get("ctY_0")),
            "phone": self._safe_string(customer.get("teL_0")),
            "vat": self._safe_string(customer.get("naF_0")),  # Code NAF
            "company_registry": self._safe_string(customer.get("crN_0")),  # SIRET
            "active": True,
            "is_airsi_eligible": is_airsi,
            "is_limit": is_limit,
            "amount_credit_limit": credit_limit,
            "code_family": self._safe_string(customer.get("tsccoD_0")),  # Code transporteur
        }

        # Ajout des champs relationnels (Many2one)
        category_id = self._get_category_id(customer.get("bccgcoD_0"))
        if category_id:
            vals["category_id"] = [(4, category_id)]  # Ajout à la relation Many2many
        
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

        # Dates de création et modification (si les champs existent dans votre modèle)
        create_date = self._safe_datetime(customer.get("credattiM_0"))
        if create_date:
            vals["create_date_sage"] = create_date
            
        update_date = self._safe_datetime(customer.get("upddattiM_0"))
        if update_date:
            vals["update_date_sage"] = update_date

        return vals

    # ----------------------------------------------------------
    # MÉTHODES AUXILIAIRES POUR LES RELATIONS Many2one
    # ----------------------------------------------------------
    def _get_category_id(self, name):
        """Récupère ou crée une catégorie de partenaire"""
        if not name:
            return False
        try:
            rec = self.env["res.partner.category"].search([("name", "ilike", name)], limit=1)
            if rec:
                return rec.id
            # Création automatique si n'existe pas
            new_rec = self.env["res.partner.category"].create({"name": name})
            _logger.info("➕ Catégorie créée : %s", name)
            return new_rec.id
        except Exception as e:
            _logger.warning("⚠️ Erreur création catégorie '%s' : %s", name, str(e))
            return False

    def _get_currency_id(self, name):
        """Récupère une devise (ne crée pas automatiquement)"""
        if not name:
            return False
        try:
            rec = self.env["res.currency"].search([("name", "=", name)], limit=1)
            if rec:
                return rec.id
            _logger.warning("⚠️ Devise introuvable : %s", name)
            return False
        except Exception as e:
            _logger.warning("⚠️ Erreur recherche devise '%s' : %s", name, str(e))
            return False

    def _get_responsible_id(self, name):
        """Récupère un utilisateur responsable (ne crée pas automatiquement)"""
        if not name:
            return False
        try:
            rec = self.env["res.users"].search([("name", "ilike", name)], limit=1)
            if rec:
                return rec.id
            _logger.debug("ℹ️ Utilisateur introuvable : %s", name)
            return False
        except Exception as e:
            _logger.warning("⚠️ Erreur recherche utilisateur '%s' : %s", name, str(e))
            return False

    def _get_property_payment_term_id(self, name):
        """Récupère ou crée une condition de paiement"""
        if not name:
            return False
        try:
            rec = self.env["account.payment.term"].search([("name", "ilike", name)], limit=1)
            if rec:
                return rec.id
            # Création automatique d'une condition de paiement simple
            new_rec = self.env["account.payment.term"].create({
                "name": name,
                "note": f"Condition de paiement: {name}",
            })
            _logger.info("➕ Condition de paiement créée : %s", name)
            return new_rec.id
        except Exception as e:
            _logger.warning("⚠️ Erreur création condition paiement '%s' : %s", name, str(e))
            return False