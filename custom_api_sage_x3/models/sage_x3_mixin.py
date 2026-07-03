import time
import logging
import requests

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT     = 30
MAX_RETRIES = 3
TOKEN_TTL   = 3600  # 1 heure

# Cache token en mémoire (partagé entre toutes les instances du worker)
_TOKEN_CACHE  = {}   # {company_id: token}
_TOKEN_EXPIRY = {}   # {company_id: timestamp}


class SageX3Mixin(models.AbstractModel):
    _name        = 'sage.x3.mixin'
    _description = 'Mixin SAGE X3 — Config, auth, cache token, HTTP'

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def _get_sage_x3_config(self):
        """
        Retourne un dict de configuration depuis ir.config_parameter.

        Clés à créer dans Paramètres > Technique > Paramètres système :
            sage_x3.base_url  →  http://172.16.2.150:8030
            sage_x3.username  →  odoo
            sage_x3.password  →  InterfaceX3_Odoo
        """
        params   = self.env['ir.config_parameter'].sudo()
        base_url = params.get_param('sage_x3.base_url', 'http://172.16.2.150:8030')
        username = params.get_param('sage_x3.username', 'odoo')
        password = params.get_param('sage_x3.password', 'InterfaceX3_Odoo')

        return {
            'base_url':       base_url,
            'username':       username,
            'password':       password,
            'auth_url':       f"{base_url}/api/Auth/login",
            'accounting_url': f"{base_url}/api/AccountingEntries/batch",
            'customers_url':  f"{base_url}/api/Customers",
            'items_url':      f"{base_url}/api/Items",
            'orders_url':     f"{base_url}/api/Orders/batch",
            'deliveries_url': f"{base_url}/api/Orders/deliveries",
        }

    # =========================================================================
    # HELPERS MÉTIER
    # =========================================================================

    def _get_company_code(self, company):
        """Retourne un code société robuste (code > lib_company > 5 premiers caractères)."""
        return (
            getattr(company, 'lib_company', None)
            or company.name[:5]
        ).upper()

    def _build_ligne(self, site, compte, sens, montant, libelle, tiers='', devise='XOF'):
        """
        Construit une ligne d'écriture au format SAGE X3 (noms de champs français).

        Format attendu par l'API :
          { "site": "VRIDI", "compte": "41110000", "tiers": "CLI01",
            "libelle": "...", "sens": 1, "montant": 10000, "devise": "XOF" }

        sens : 1 = Débit | -1 = Crédit
        tiers: code tiers SAGE X3 (vide si pas de tiers)
        """
        ligne = {
            "site":    site,
            "compte":  compte,
            "libelle": libelle,
            "sens":    sens,
            "montant": montant,
            "devise":  devise,
        }
        if tiers:
            ligne["tiers"] = tiers
        return ligne

    def _build_ecriture(self, type_piece, site, date_ddmmyy, journal,
                        libelle, lignes, devise='XOF', echeances=None,
                        date_echeance=None):
        """
        Construit une écriture au format SAGE X3.

        Format attendu :
          { "type": "FACLI", "site": "VRIDI", "date": "230326",
            "journal": "VTE", "libelle": "...", "devise": "XOF",
            "dateEcheance": "230426", "lignes": [...], "echeances": [...] }

        date_ddmmyy   : chaîne au format YYMMDD (ex: "230326" pour le 23/03/2026)
        date_echeance : date d'échéance unique de l'écriture (même format),
                        cf. _build_echeances. Omise si vide.
        echeances     : liste optionnelle d'échéances (cf. _build_echeances).
                        Omise du payload si vide, pour ne pas modifier les
                        écritures existantes qui n'en ont pas besoin
                        (ENCAI, DECAI, AVCLI...).
        """
        ecriture = {
            "type":    type_piece,
            "site":    site,
            "date":    date_ddmmyy,
            "journal": journal,
            "libelle": libelle,
            "devise":  devise,
            "lignes":  lignes,
        }
        if date_echeance:
            ecriture["dateEcheance"] = date_echeance
        if echeances:
            ecriture["echeances"] = echeances
        return ecriture

    def _build_echeances(self, partner, montant, sens, date_ref):
        """
        Construit les échéances SAGE X3 pour une facture "mise en compte"
        (client à crédit), à partir de la condition de paiement du client.

        Retourne un tuple (date_echeance, echeances) :
        - date_echeance : échéance finale de l'écriture (dernière ligne de
                          la condition de paiement), format DDMMYY — l'API
                          SAGE X3 n'accepte qu'une seule date par écriture,
                          pas une par échéance.
        - echeances     : liste de {montant, sens, modeReglement}, le
                          montant étant réparti entre les lignes de la
                          condition de paiement (pourcentage ou montant
                          fixe), la dernière ligne absorbant l'écart
                          d'arrondi pour que la somme égale exactement
                          `montant`.

        Lève une UserError si le client n'a pas de condition de paiement
        configurée (property_payment_term_id), car aucune échéance ne peut
        alors être calculée.
        """
        term = partner.property_payment_term_id
        if not term:
            raise UserError(
                f"Aucune condition de paiement configurée pour le client {partner.name} "
                f"— nécessaire pour calculer l'échéance SAGE X3."
            )
        if not term.line_ids:
            raise UserError(
                f"La condition de paiement '{term.name}' du client {partner.name} "
                f"n'a aucune ligne — impossible de calculer l'échéance SAGE X3."
            )

        mode_reglement = term.payment_method
        montant = round(montant, 2)
        residual = montant
        echeances = []

        for idx, line in enumerate(term.line_ids):
            is_last = idx == len(term.line_ids) - 1
            if is_last:
                line_montant = residual
            elif line.value == 'fixed':
                line_montant = round(line.value_amount, 2)
            else:
                line_montant = round(montant * (line.value_amount / 100.0), 2)

            residual = round(residual - line_montant, 2)

            echeances.append({
                "montant":       line_montant,
                "sens":          sens,
                "modeReglement": mode_reglement,
            })

        date_echeance = term.line_ids[-1]._get_due_date(date_ref).strftime("%d%m%y")
        return date_echeance, echeances

    # =========================================================================
    # AUTHENTIFICATION AVEC CACHE TOKEN
    # =========================================================================

    def _authenticate_sage_x3(self):
        """Authentification avec cache token TTL 1h. Évite un appel par document."""
        company_id = self.env.company.id
        now        = time.time()

        if company_id in _TOKEN_CACHE and now < _TOKEN_EXPIRY.get(company_id, 0):
            _logger.debug("🔑 Token SAGE X3 depuis le cache (société %s)", company_id)
            return _TOKEN_CACHE[company_id]

        config = self._get_sage_x3_config()

        try:
            _logger.debug("🔐 Authentification SAGE X3 (société %s)...", company_id)
            response = requests.post(
                config['auth_url'],
                json={"username": config['username'], "password": config['password']},
                timeout=15,
            )

            if response.status_code in (200, 201):
                token = response.json().get("token")
                if token:
                    _TOKEN_CACHE[company_id]  = token
                    _TOKEN_EXPIRY[company_id] = now + TOKEN_TTL
                    _logger.debug("✅ Authentification réussie")
                    return token
                _logger.error("❌ Token absent dans la réponse")
                return None

            _logger.error("❌ Échec auth HTTP %s", response.status_code)
            return None

        except Exception as e:
            _logger.error("❌ Erreur authentification: %s", str(e))
            return None

    def _invalidate_sage_x3_token(self):
        """Force le renouvellement du token au prochain appel (ex: 401)."""
        company_id = self.env.company.id
        _TOKEN_CACHE.pop(company_id, None)
        _TOKEN_EXPIRY.pop(company_id, None)

    # =========================================================================
    # POST HTTP AVEC RETRY
    # =========================================================================

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """POST avec retry et backoff (2s, 4s, 6s). Gère le 401 automatiquement."""
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                _logger.debug("📡 POST tentative %s/%s: %s", attempt + 1, MAX_RETRIES, url)
                response = requests.post(url, headers=headers, json=data, timeout=timeout)

                if response.status_code in (200, 201):
                    return response

                if response.status_code == 401 and attempt == 0:
                    _logger.warning("🔄 Token expiré (401) — renouvellement...")
                    self._invalidate_sage_x3_token()
                    new_token = self._authenticate_sage_x3()
                    if new_token:
                        headers = {**headers, "Authorization": f"Bearer {new_token}"}
                    continue

                _logger.warning("⚠️ HTTP %s (tentative %s/%s)",
                                response.status_code, attempt + 1, MAX_RETRIES)
                last_exception = Exception(f"HTTP {response.status_code}: {response.text}")

            except requests.exceptions.Timeout:
                _logger.warning("⏱️ Timeout (tentative %s/%s)", attempt + 1, MAX_RETRIES)
                last_exception = Exception("Timeout")

            except Exception as e:
                _logger.warning("❌ Erreur réseau (tentative %s/%s): %s",
                                attempt + 1, MAX_RETRIES, str(e))
                last_exception = e

            if attempt < MAX_RETRIES - 1:
                wait = 2 * (attempt + 1)
                _logger.info("⏳ Attente %ss avant retry...", wait)
                time.sleep(wait)

        raise last_exception or Exception("Échec après tous les retries")

    # =========================================================================
    # GET HTTP AVEC RETRY
    # =========================================================================

    def _safe_get(self, url, headers, params=None, timeout=TIMEOUT):
        """GET avec retry (pour imports paginés)."""
        last_exc = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
                _logger.warning("⚠️ HTTP %s (tentative %s)", response.status_code, attempt)
                last_exc = Exception(f"HTTP {response.status_code}")
            except requests.exceptions.RequestException as e:
                _logger.warning("⚠️ Exception réseau (tentative %s): %s", attempt, str(e))
                last_exc = e
            time.sleep(5)

        raise UserError(f"Échec GET après {MAX_RETRIES} tentatives : {last_exc}")

    # =========================================================================
    # EXTRACTION DU NUMÉRO DE PIÈCE
    # =========================================================================

    def _extract_x3_results(self, response, fallback_reference):
        """Extrait message + numéro pour chaque pièce retournée par SAGE X3."""
        results = []

        try:
            response_data = response.json()

            if not isinstance(response_data, list):
                return [{
                    "message": "Réponse invalide SAGE X3",
                    "piece": fallback_reference
                }]

            for res in response_data:
                if res.get("success"):
                    results.append({
                        "message": res.get("message", ""),
                        "piece": res.get("x3DocumentNumber") or fallback_reference
                    })
                else:
                    results.append({
                        "message": res.get("message", "Erreur inconnue"),
                        "piece": None
                    })

        except Exception as e:
            _logger.warning(f"⚠️ Erreur extraction X3: {e}")
            return [{
                "message": "Erreur lecture réponse X3",
                "piece": fallback_reference
            }]

        return results
