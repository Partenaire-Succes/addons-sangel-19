import requests
import time
import logging
import json
from odoo import models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 30
MAX_RETRIES = 3

# Cache token en mémoire (par process Odoo)
# Structure : { db_name: { 'token': str, 'expires_at': float } }
_TOKEN_CACHE = {}


class SageX3Mixin(models.AbstractModel):
    """
    Mixin réutilisable pour tous les modèles qui communiquent avec SAGE X3.
    Centralise : configuration, authentification, envoi HTTP avec retry.
    """
    _name = 'sage.x3.mixin'
    _description = 'Mixin SAGE X3'

    # -------------------------------------------------------------------------
    # Configuration (lue depuis ir.config_parameter)
    # -------------------------------------------------------------------------

    def _get_sage_x3_config(self):
        """
        Retourne la configuration SAGE X3 depuis les paramètres système.
        Configurable dans : Paramètres > Technique > Paramètres système
        Clés attendues :
            sage_x3.base_url   → ex. http://172.16.2.150:8040
            sage_x3.username   → ex. odoo
            sage_x3.password   → ex. InterfaceX3_Odoo
        """
        get = lambda key: self.env['ir.config_parameter'].sudo().get_param(key)

        base_url = get('sage_x3.base_url')
        username = get('sage_x3.username')
        password = get('sage_x3.password')

        if not base_url or not username or not password:
            raise UserError(
                "Configuration SAGE X3 incomplète.\n"
                "Veuillez renseigner dans Paramètres > Technique > Paramètres système :\n"
                "  • sage_x3.base_url\n"
                "  • sage_x3.username\n"
                "  • sage_x3.password"
            )

        return {
            'base_url': base_url.rstrip('/'),
            'auth_url': f"{base_url.rstrip('/')}/api/Auth/login",
            'accounting_url': f"{base_url.rstrip('/')}/api/Accounting/entries/batch",
            'username': username,
            'password': password,
        }

    # -------------------------------------------------------------------------
    # Authentification avec cache token
    # -------------------------------------------------------------------------

    def _authenticate_sage_x3(self):
        """
        Authentification SAGE X3 avec cache en mémoire.
        Le token est réutilisé pendant 50 minutes (durée conservative).
        Un nouveau token est demandé à l'expiration ou en cas d'erreur 401.
        """
        db_name = self.env.cr.dbname
        cache = _TOKEN_CACHE.get(db_name, {})

        # Vérifier si le token en cache est encore valide
        if cache.get('token') and cache.get('expires_at', 0) > time.time():
            _logger.debug("🔑 Token SAGE X3 en cache (valide)")
            return cache['token']

        # Obtenir un nouveau token
        token = self._fetch_new_sage_x3_token()
        if token:
            _TOKEN_CACHE[db_name] = {
                'token': token,
                'expires_at': time.time() + 50 * 60  # 50 minutes
            }
        return token

    def _fetch_new_sage_x3_token(self):
        """Appel HTTP d'authentification, retourne le token ou None."""
        try:
            config = self._get_sage_x3_config()
            _logger.debug("🔐 Authentification SAGE X3...")

            response = requests.post(
                config['auth_url'],
                json={"username": config['username'], "password": config['password']},
                timeout=15
            )

            if response.status_code in (200, 201):
                token = response.json().get("token")
                if token:
                    _logger.debug("✅ Authentification SAGE X3 réussie")
                    return token
                _logger.error("❌ Token absent dans la réponse SAGE X3")
                return None

            _logger.error("❌ Échec authentification SAGE X3: HTTP %s", response.status_code)
            return None

        except Exception as e:
            _logger.error("❌ Erreur authentification SAGE X3: %s", str(e))
            return None

    def _invalidate_sage_x3_token(self):
        """Invalide le cache token (à appeler sur réponse 401)."""
        _TOKEN_CACHE.pop(self.env.cr.dbname, None)

    # -------------------------------------------------------------------------
    # Envoi HTTP avec retry
    # -------------------------------------------------------------------------

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """
        POST HTTP avec retry automatique et backoff progressif.
        Sur réponse 401, invalide le token et lève une exception claire.
        Backoff : 2s, 4s, 6s entre les tentatives.
        """
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                _logger.debug("📡 Tentative %s/%s: POST %s", attempt + 1, MAX_RETRIES, url)

                response = requests.post(url, headers=headers, json=data, timeout=timeout)

                if response.status_code in (200, 201):
                    _logger.debug("✅ Requête SAGE X3 réussie")
                    return response

                # Token expiré → invalider le cache immédiatement
                if response.status_code == 401:
                    self._invalidate_sage_x3_token()
                    raise Exception("Token SAGE X3 invalide ou expiré (401)")

                _logger.warning(
                    "⚠️ HTTP %s (tentative %s/%s) — %s",
                    response.status_code, attempt + 1, MAX_RETRIES, response.text[:200]
                )
                last_exception = Exception(f"HTTP {response.status_code}: {response.text}")

            except requests.exceptions.Timeout:
                _logger.warning("⏱️ Timeout (tentative %s/%s)", attempt + 1, MAX_RETRIES)
                last_exception = Exception("Timeout de connexion SAGE X3")

            except Exception as e:
                _logger.warning("❌ Erreur tentative %s/%s: %s", attempt + 1, MAX_RETRIES, str(e))
                last_exception = e

            # Backoff avant nouvelle tentative (sauf dernière)
            if attempt < MAX_RETRIES - 1:
                wait_time = 2 * (attempt + 1)
                _logger.info("⏳ Attente %ss avant nouvelle tentative...", wait_time)
                time.sleep(wait_time)

        raise last_exception or Exception("Échec après tous les retries SAGE X3")

    # -------------------------------------------------------------------------
    # Helper commun : code société
    # -------------------------------------------------------------------------

    def _get_company_code(self, company):
        """
        Retourne le code court de la société (max 5 caractères, majuscules).
        Essaie dans l'ordre : company.code → company.lib_company → 5 premiers chars du nom.
        """
        code = (
            getattr(company, 'code', None)
            or getattr(company, 'lib_company', None)
            or company.name[:5]
        )
        return (code or 'UNKNW').upper()
