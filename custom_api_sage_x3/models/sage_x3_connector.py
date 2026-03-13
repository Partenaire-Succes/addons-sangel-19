# -*- coding: utf-8 -*-
"""
Intégration SAGE X3 — Commandes d'achat
Auteur  : Koua Alexandre
Version : 2.0.0 (production)
"""

import time
import threading
import logging
import json
from datetime import datetime, timedelta
from collections import defaultdict

import requests

from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ============================================================
# VALEURS PAR DÉFAUT (surchargeables via ir.config_parameter)
# ============================================================
_DEFAULT_TIMEOUT     = 30
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BATCH_SIZE  = 100
_DEFAULT_AUTH_PATH   = "/api/Auth/login"
_DEFAULT_ORDERS_PATH = "/api/Orders/batch"
_DEFAULT_DELIV_PATH  = "/api/Orders/deliveries"


# ============================================================
# EXTENSION res.company  —  champs SAGE X3 par société
# ============================================================
class ResCompanySageX3(models.Model):
    _inherit = "res.company"

    sage_x3_site_vente  = fields.Char(
        string="SAGE X3 — Site de vente",
        help="Code du site de vente utilisé lors de l'envoi des commandes à SAGE X3 (ex: VRIDI).",
        default="VRIDI",
    )
    sage_x3_client_code = fields.Char(
        string="SAGE X3 — Code client",
        help="Code client SAGE X3 associé à cette société (ex: 01).",
        default="01",
    )
    sage_x3_magasin     = fields.Char(
        string="SAGE X3 — Magasin",
        help="Nom du magasin SAGE X3 associé à cette société.",
    )


# ============================================================
# INTÉGRATION SAGE X3  —  Commandes d'achat
# ============================================================
class PurchaseOrderSageX3(models.Model):
    _inherit = "purchase.order"

    # ----------------------------------------------------------
    # CONFIGURATION CENTRALISÉE
    # ----------------------------------------------------------

    def _get_config(self):
        """
        Lit toute la configuration SAGE X3 depuis ir.config_parameter.

        Clés requises :
            sage_x3.base_url   — URL de base de l'API (ex: http://172.16.2.150:8030)
            sage_x3.username   — Nom d'utilisateur API
            sage_x3.password   — Mot de passe API

        Clés optionnelles (valeurs par défaut appliquées si absentes) :
            sage_x3.timeout          (défaut: 30)
            sage_x3.max_retries      (défaut: 3)
            sage_x3.batch_size       (défaut: 100)
            sage_x3.auth_path        (défaut: /api/Auth/login)
            sage_x3.orders_path      (défaut: /api/Orders/batch)
            sage_x3.deliveries_path  (défaut: /api/Orders/deliveries)
        """
        cfg = self.env['ir.config_parameter'].sudo()

        base_url = cfg.get_param('sage_x3.base_url', '').rstrip('/')
        if not base_url:
            raise UserError(
                "L'URL de base SAGE X3 n'est pas configurée.\n"
                "Allez dans Paramètres › Technique › Paramètres système\n"
                "et définissez la clé : sage_x3.base_url"
            )

        username = cfg.get_param('sage_x3.username', '')
        password = cfg.get_param('sage_x3.password', '')
        if not username or not password:
            raise UserError(
                "Les identifiants SAGE X3 ne sont pas configurés.\n"
                "Définissez les clés suivantes dans les paramètres système :\n"
                "  • sage_x3.username\n"
                "  • sage_x3.password"
            )

        return {
            'base_url':        base_url,
            'username':        username,
            'password':        password,
            'timeout':         int(cfg.get_param('sage_x3.timeout',         _DEFAULT_TIMEOUT)),
            'max_retries':     int(cfg.get_param('sage_x3.max_retries',     _DEFAULT_MAX_RETRIES)),
            'batch_size':      int(cfg.get_param('sage_x3.batch_size',      _DEFAULT_BATCH_SIZE)),
            'auth_path':       cfg.get_param('sage_x3.auth_path',       _DEFAULT_AUTH_PATH),
            'orders_path':     cfg.get_param('sage_x3.orders_path',     _DEFAULT_ORDERS_PATH),
            'deliveries_path': cfg.get_param('sage_x3.deliveries_path', _DEFAULT_DELIV_PATH),
        }

    # ----------------------------------------------------------
    # AUTHENTIFICATION AVEC CACHE TOKEN
    # ----------------------------------------------------------

    def _authenticate_sage_x3(self, cfg):
        """
        Authentification SAGE X3 avec mise en cache du token dans
        ir.config_parameter. Le token est réutilisé jusqu'à 5 min
        avant son expiration (durée supposée : 1 h).
        """
        param = self.env['ir.config_parameter'].sudo()
        cached_token  = param.get_param('sage_x3._cached_token')
        cached_expiry = param.get_param('sage_x3._token_expiry')

        if cached_token and cached_expiry:
            try:
                if datetime.fromisoformat(cached_expiry) > datetime.now() + timedelta(minutes=5):
                    _logger.debug("🔑 Token SAGE X3 en cache encore valide.")
                    return cached_token
            except (ValueError, TypeError):
                pass  # expiry corrompu → réauthentification

        _logger.info("🔑 Obtention d'un nouveau token SAGE X3...")
        auth_url = cfg['base_url'] + cfg['auth_path']

        try:
            resp = requests.post(
                auth_url,
                json={"username": cfg['username'], "password": cfg['password']},
                timeout=15,
            )
            resp.raise_for_status()
            token = resp.json().get("token")
            if not token:
                _logger.error("❌ Réponse auth sans token: %s", resp.text[:300])
                raise UserError(
                    "SAGE X3 n'a pas retourné de token d'authentification. "
                    "Vérifiez les identifiants configurés."
                )

            expiry = (datetime.now() + timedelta(minutes=55)).isoformat()
            param.set_param('sage_x3._cached_token', token)
            param.set_param('sage_x3._token_expiry',  expiry)
            _logger.info("✅ Nouveau token SAGE X3 obtenu, valide jusqu'à %s", expiry)
            return token

        except requests.exceptions.Timeout:
            raise UserError(
                "Délai d'attente dépassé lors de la connexion à SAGE X3.\n"
                "Vérifiez que l'URL est correcte et que le serveur est accessible."
            )
        except requests.exceptions.ConnectionError as e:
            raise UserError(f"Impossible de se connecter à SAGE X3 :\n{e}")
        except requests.exceptions.HTTPError as e:
            raise UserError(f"Erreur HTTP lors de l'authentification SAGE X3 :\n{e}")

    def _get_auth_headers(self, cfg):
        """Retourne les en-têtes HTTP authentifiés prêts à l'emploi."""
        token = self._authenticate_sage_x3(cfg)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    # ----------------------------------------------------------
    # REQUÊTES HTTP AVEC RETRY EXPONENTIEL
    # ----------------------------------------------------------

    def _safe_request(self, method, url, cfg, **kwargs):
        """
        Exécute une requête HTTP (GET ou POST) avec retry exponentiel.

        Args:
            method : 'GET' ou 'POST'
            url    : URL complète
            cfg    : dictionnaire de configuration (_get_config)
            **kwargs : paramètres supplémentaires passés à requests

        Returns:
            requests.Response

        Raises:
            UserError si tous les retries échouent
        """
        max_retries = cfg['max_retries']
        timeout     = cfg['timeout']
        last_exc    = None

        for attempt in range(max_retries):
            try:
                resp = requests.request(method, url, timeout=timeout, **kwargs)
                if resp.status_code in (200, 201):
                    return resp
                _logger.warning(
                    "⚠️ %s %s — HTTP %s (tentative %s/%s)",
                    method, url, resp.status_code, attempt + 1, max_retries
                )
            except requests.exceptions.Timeout as e:
                last_exc = e
                _logger.warning("⏱️ Timeout %s (tentative %s/%s)", method, attempt + 1, max_retries)
            except requests.exceptions.ConnectionError as e:
                last_exc = e
                _logger.warning("🔌 Connexion échouée %s (tentative %s/%s)", method, attempt + 1, max_retries)
            except requests.exceptions.RequestException as e:
                last_exc = e
                _logger.warning("❌ Erreur requête %s (tentative %s/%s): %s", method, attempt + 1, max_retries, e)

            if attempt < max_retries - 1:
                wait = 2 ** attempt  # backoff: 1 s, 2 s, 4 s
                _logger.info("⏳ Retry dans %s s...", wait)
                time.sleep(wait)

        detail = str(last_exc) if last_exc else "Erreur inconnue"
        raise UserError(
            f"Impossible de joindre SAGE X3 après {max_retries} tentatives.\n"
            f"URL : {url}\nDétail : {detail}"
        )

    # ----------------------------------------------------------
    # ACTIONS UTILISATEUR — SOUMISSION COMMANDE
    # ----------------------------------------------------------

    def action_submit_urgent_command(self):
        """Soumettre immédiatement une commande marquée 'urgente'."""
        self.ensure_one()
        if self.type_command != 'urgent':
            raise UserError(
                "La commande doit être marquée comme urgente pour utiliser cette action."
            )
        return self.action_submit_to_sage_x3()

    def action_submit_to_sage_x3(self):
        """Soumettre la commande courante à SAGE X3."""
        self.ensure_one()

        if self.state not in ['draft', 'sent']:
            raise UserError(
                "Seules les commandes en brouillon ou envoyées peuvent être soumises à SAGE X3."
            )
        if self.sage_x3_validated:
            raise UserError("Cette commande a déjà été validée par SAGE X3.")

        try:
            self._submit_to_sage_x3()
            if self.sage_x3_validated:
                self.button_confirm()

            notif_type = 'success' if self.sage_x3_validated else 'warning'
            title      = '✅ Succès' if self.sage_x3_validated else '⚠️ Attention'
            message    = self.sage_x3_response_message or self.sage_x3_error or 'Traité.'
            return self._action_notification(title, message, notif_type)

        except UserError as e:
            return self._action_notification('❌ Erreur', str(e), 'danger', sticky=True)
        except Exception as e:
            _logger.exception("❌ Erreur inattendue soumission SAGE X3 — %s", self.name)
            return self._action_notification('❌ Erreur inattendue', str(e), 'danger', sticky=True)

    def _submit_to_sage_x3(self):
        """Logique métier : prépare et envoie la commande à SAGE X3."""
        self.ensure_one()
        cfg     = self._get_config()
        headers = self._get_auth_headers(cfg)
        payload = self._prepare_order_payload()
        url     = cfg['base_url'] + cfg['orders_path']

        resp      = self._safe_request('POST', url, cfg, headers=headers, json=payload)
        resp_data = resp.json()

        if not (isinstance(resp_data, list) and resp_data):
            raise UserError("Réponse SAGE X3 inattendue (format incorrect).")

        result  = resp_data[0]
        success = result.get("success", False)
        message = result.get("message", "")

        self.write({
            'sage_x3_submitted':      True,
            'sage_x3_validated':      success,
            'sage_x3_submitted_date': fields.Datetime.now(),
            'sage_x3_response_message': message if success else False,
            'sage_x3_error':          False if success else message,
        })
        self.message_post(
            body=f"{'✅ Validée' if success else '❌ Rejetée'}\n{message}",
            subject=f"{'✅' if success else '❌'} SAGE X3",
        )

        if not success:
            raise UserError(f"Commande rejetée par SAGE X3 : {message}")
        return True

    def _prepare_order_payload(self):
        """Construit le dictionnaire JSON envoyé à SAGE X3."""
        self.ensure_one()

        if not self.partner_id:
            raise UserError("La commande doit avoir un fournisseur avant d'être soumise.")
        if not self.order_line:
            raise UserError("La commande ne contient aucune ligne de produit.")

        items = []
        for idx, line in enumerate(self.order_line, start=1):
            if not line.product_id.default_code:
                raise UserError(
                    f"Le produit « {line.product_id.name} » n'a pas de référence interne.\n"
                    "Veuillez en définir une avant de soumettre la commande."
                )
            items.append({
                "ligne":      idx * 1000,
                "article":    line.product_id.default_code,
                "TexteLigne": line.name or line.product_id.name or "",
                "quantite":   max(line.product_qty, 0.01),
            })

        company = self.company_id
        return {
            "commandes": [{
                "siteVente":               company.sage_x3_site_vente  or "VRIDI",
                "DateCommande":            (self.date_order or datetime.now()).isoformat(),
                "Client":                  company.sage_x3_client_code or "01",
                "Devise":                  self.currency_id.name       or "XOF",
                "Magasin":                 company.sage_x3_magasin     or company.name or "PRINCIPAL",
                "ReferenceCommandeClient": self.name,
                "items":                   items,
            }]
        }

    # ----------------------------------------------------------
    # ACTIONS UTILISATEUR — IMPORT DES LIVRAISONS
    # ----------------------------------------------------------

    def action_import_deliveries(self):
        """
        Lance l'import des livraisons SAGE X3.
        Utilise queue_job si disponible, sinon un thread en arrière-plan.
        """
        model = self.env['purchase.order']

        if 'queue.job' in self.env:
            try:
                pending = self.env['queue.job'].search([
                    ('name',  'ilike', 'Import livraisons SAGE X3'),
                    ('state', 'in',    ['pending', 'enqueued', 'started']),
                ])
                if pending:
                    return self._action_notification(
                        '⚠️ Import en cours',
                        "Un import est déjà en cours d'exécution. Veuillez patienter.",
                        'warning',
                    )

                model.with_delay(
                    description="Import livraisons SAGE X3",
                    priority=10,
                    max_retries=2,
                    eta=datetime.now() + timedelta(seconds=5),
                )._job_import_deliveries()

                return self._action_notification(
                    '🚀 Import planifié',
                    "L'import démarrera dans 5 secondes.\n"
                    "Suivez la progression dans Paramètres › Queue Jobs.",
                    'info',
                )
            except Exception as e:
                _logger.error("❌ queue_job indisponible (%s), fallback threading.", e)

        # Fallback : threading
        _logger.info("📌 Import SAGE X3 via threading (queue_job non installé).")
        t = threading.Thread(
            target=self.__class__._threaded_import_deliveries,
            args=(self.env.cr.dbname, self.env.uid, dict(self.env.context)),
            daemon=True,
        )
        t.start()
        return self._action_notification(
            '🚀 Import lancé',
            "L'import des livraisons s'exécute en arrière-plan.",
            'info',
        )

    @classmethod
    def _threaded_import_deliveries(cls, dbname, uid, context):
        """Exécuté dans un thread séparé (fallback sans queue_job)."""
        try:
            import odoo
            registry = odoo.registry(dbname)
            with registry.cursor() as cr:
                env = odoo.api.Environment(cr, uid, context)
                env['purchase.order']._job_import_deliveries()
                cr.commit()
        except Exception:
            _logger.exception("❌ [THREAD] Erreur import SAGE X3")

    def action_import_all_receive_external_source(self):
        """
        Import en masse : met à jour toutes les commandes confirmées
        de la société courante à partir des livraisons SAGE X3.
        """
        purchases = self.search([
            ('company_id', '=', self.env.company.id),
            ('state',      '=', 'purchase'),
        ])

        ok = ko = 0
        errors = []

        for idx, purchase in enumerate(purchases, 1):
            try:
                purchase._job_import_deliveries()
                ok += 1
                if idx % 10 == 0:
                    self.env.cr.commit()
            except Exception as e:
                ko += 1
                errors.append(f"{purchase.name}: {e}")
                _logger.error("❌ Import commande %s: %s", purchase.name, e)

        self.env.cr.commit()
        _logger.info("📊 Import en masse — Succès: %s | Erreurs: %s", ok, ko)
        return {'success': ok, 'errors': ko, 'error_details': errors}

    # ----------------------------------------------------------
    # JOB PRINCIPAL D'IMPORT
    # ----------------------------------------------------------

    @api.model
    def _job_import_deliveries(self):
        """
        Récupère et intègre les livraisons SAGE X3 pour la société courante.
        Conçu pour être exécuté par queue_job, un thread ou un cron.
        """
        t0      = datetime.now()
        company = self.env.company

        try:
            cfg     = self._get_config()
            headers = self._get_auth_headers(cfg)
            headers.pop('Content-Type', None)  # GET n'a pas besoin de Content-Type

            last_import = self._get_last_import_date(company.id)
            params      = {'since': last_import.isoformat()} if last_import else None

            _logger.info("📡 [%s] Récupération livraisons depuis %s",
                         company.name, last_import or "début")

            url  = cfg['base_url'] + cfg['deliveries_path']
            resp = self._safe_request('GET', url, cfg, headers=headers, params=params)

            deliveries = self._parse_deliveries_response(resp.text)
            if not deliveries:
                _logger.info("✅ [%s] Aucune livraison à traiter.", company.name)
                return {'updated': 0, 'errors': 0}

            _logger.info("📦 %s livraisons reçues au total.", len(deliveries))

            filtered = self._filter_deliveries_by_company(deliveries, company)
            if not filtered:
                _logger.info("✅ [%s] Aucune livraison pour cette société.", company.name)
                return {'updated': 0, 'errors': 0, 'filtered': len(deliveries)}

            _logger.info("📦 [%s] %s livraisons à traiter.", company.name, len(filtered))

            order_cache, product_cache = self._preload_data(filtered, company.id)
            stats = self._process_deliveries_in_batches(
                filtered, order_cache, product_cache, company.id, cfg['batch_size']
            )

            self._update_last_import_date(company.id)
            duration = (datetime.now() - t0).total_seconds()
            self._notify_import_completion(stats, duration, company.name)
            return stats

        except UserError:
            raise
        except Exception as e:
            _logger.exception("❌ [JOB] Erreur fatale import [%s]", company.name)
            self._notify_import_error(str(e), company.name)
            raise

    # ----------------------------------------------------------
    # PARSING & FILTRAGE
    # ----------------------------------------------------------

    def _parse_deliveries_response(self, response_text):
        """Parse le JSON de réponse des livraisons SAGE X3."""
        if not response_text:
            return []

        size_mb = len(response_text) / 1_000_000
        if size_mb > 5:
            _logger.warning("⚠️ JSON volumineux : %.1f MB", size_mb)

        try:
            raw = json.loads(response_text)
            deliveries = []

            if isinstance(raw, list):
                deliveries = raw
            elif isinstance(raw, dict):
                livraison = raw.get("livraison", {})
                if isinstance(livraison, dict):
                    for items_list in livraison.values():
                        if isinstance(items_list, list):
                            deliveries.extend(items_list)
                elif isinstance(livraison, list):
                    deliveries = livraison

            deliveries.sort(key=lambda x: x.get('dateCommande', ''), reverse=True)
            return deliveries

        except json.JSONDecodeError as e:
            _logger.error("❌ JSON invalide reçu de SAGE X3 : %s", e)
            return []

    def _filter_deliveries_by_company(self, deliveries, company):
        """Retourne uniquement les livraisons appartenant à la société courante."""
        if not deliveries:
            return []

        all_refs = {
            str(d.get("referenceCommandeClient", "")).strip()
            for d in deliveries
            if d.get("referenceCommandeClient")
        }
        if not all_refs:
            return []

        orders = self.search([
            ('name',              'in',  list(all_refs)),
            ('company_id',        '=',   company.id),
            ('sage_x3_submitted', '=',   True),
            ('sage_x3_validated', '=',   True),
        ])
        valid_refs = set(orders.mapped('name'))

        filtered = [
            d for d in deliveries
            if str(d.get("referenceCommandeClient", "")).strip() in valid_refs
        ]

        _logger.info("🔍 Filtrage [%s] : %s/%s livraisons retenues.",
                     company.name, len(filtered), len(deliveries))
        return filtered

    # ----------------------------------------------------------
    # PRÉCHARGEMENT (évite les N+1 queries)
    # ----------------------------------------------------------

    def _preload_data(self, deliveries, company_id):
        """
        Pré-charge en une seule requête SQL toutes les commandes et tous
        les produits référencés dans les livraisons.

        Returns:
            (order_cache, product_cache) — dicts {clé: id}
        """
        order_refs = {
            str(d.get("referenceCommandeClient", "")).strip()
            for d in deliveries
            if d.get("referenceCommandeClient")
        }

        _logger.info("🔄 Pré-chargement %s commandes (société ID %s)...",
                     len(order_refs), company_id)

        orders = self.search([
            ('name',              'in',  list(order_refs)),
            ('company_id',        '=',   company_id),
            ('sage_x3_submitted', '=',   True),
            ('sage_x3_validated', '=',   True),
            ('state',             'in',  ['purchase', 'to approve']),
        ])
        order_cache = {o.name: o.id for o in orders}

        all_articles = {
            item.get("article")
            for d in deliveries
            for item in d.get("items", [])
            if item.get("article")
        }

        _logger.info("🔄 Pré-chargement %s références produits...", len(all_articles))
        products = self.env['product.product'].search([
            ('default_code', 'in', list(all_articles))
        ])
        product_cache = {p.default_code: p.id for p in products}

        _logger.info("✅ Caches prêts : %s commandes, %s produits.",
                     len(order_cache), len(product_cache))
        return order_cache, product_cache

    # ----------------------------------------------------------
    # TRAITEMENT PAR LOTS
    # ----------------------------------------------------------

    def _process_deliveries_in_batches(self, deliveries, order_cache,
                                       product_cache, company_id, batch_size):
        """Traite les livraisons par lots avec commits intermédiaires."""
        total = len(deliveries)
        updated = errors = lines = skipped = 0

        for start in range(0, total, batch_size):
            end   = min(start + batch_size, total)
            batch = deliveries[start:end]
            pct   = end / total * 100

            _logger.info("🔄 Lot %s–%s / %s (%.0f%%) — société ID %s",
                         start + 1, end, total, pct, company_id)

            s = self._process_batch(batch, start, order_cache, product_cache)
            updated += s['updated']
            lines   += s['lines']
            errors  += s['errors']
            skipped += s['skipped']

            self.env.cr.commit()
            self.env.clear()

        return {
            'total':      total,
            'updated':    updated,
            'lines':      lines,
            'errors':     errors,
            'skipped':    skipped,
            'company_id': company_id,
        }

    def _process_batch(self, batch, offset, order_cache, product_cache):
        """Traite un lot de livraisons individuelles."""
        stats = {'updated': 0, 'lines': 0, 'errors': 0, 'skipped': 0}

        for i, delivery in enumerate(batch, start=offset + 1):
            ref = ""
            try:
                if not isinstance(delivery, dict):
                    stats['errors'] += 1
                    continue

                ref = str(delivery.get("referenceCommandeClient", "")).strip()
                if not ref:
                    stats['skipped'] += 1
                    continue

                order_id = order_cache.get(ref)
                if not order_id:
                    _logger.debug("⚠️ Commande '%s' absente du cache, ignorée.", ref)
                    stats['skipped'] += 1
                    continue

                order = self.browse(order_id)
                lines_count = self._update_order_lines(
                    order, delivery.get("items", []), product_cache
                )
                stats['lines'] += lines_count

                partner_ref = str(delivery.get("numeroCommande", "")).strip()
                order.write({
                    'sage_x3_delivery_received': True,
                    'sage_x3_delivery_date':     fields.Datetime.now(),
                    'partner_ref':               partner_ref or order.partner_ref,
                })
                stats['updated'] += 1

                if i % 10 == 0:
                    _logger.info("✅ %s / %s traités", i, len(batch) + offset)

            except Exception as e:
                _logger.error("❌ Erreur livraison '%s' (#%s) : %s", ref, i, e)
                stats['errors'] += 1

        return stats

    # ----------------------------------------------------------
    # MISE À JOUR DES LIGNES DE COMMANDE
    # ----------------------------------------------------------

    def _update_order_lines(self, order, items, product_cache):
        """
        Met à jour le prix unitaire et la quantité des lignes de commande
        en fonction des données reçues de SAGE X3.
        """
        if not items:
            return 0

        updates = defaultdict(dict)

        for item in items:
            article = item.get("article")
            if not article:
                continue

            product_id = product_cache.get(article)
            if not product_id:
                _logger.debug("⚠️ Article '%s' introuvable dans le cache produits.", article)
                continue

            matching = order.order_line.filtered(lambda l: l.product_id.id == product_id)
            if not matching:
                continue

            line       = matching[0]
            unit_price = item.get("prix")
            quantity   = item.get("quantite")

            if unit_price is not None:
                try:
                    unit_price = float(unit_price)
                    if unit_price != line.price_unit:
                        updates[line.id]['price_unit'] = unit_price
                except (ValueError, TypeError):
                    _logger.warning("⚠️ Prix invalide pour l'article '%s': %s", article, unit_price)

            if quantity is not None:
                try:
                    quantity = float(quantity)
                    if quantity > 0:
                        updates[line.id]['quantity'] = quantity
                except (ValueError, TypeError):
                    _logger.warning("⚠️ Quantité invalide pour l'article '%s': %s", article, quantity)

        updated = 0
        for line_id, vals in updates.items():
            line = self.env['purchase.order.line'].browse(line_id)
            if 'price_unit' in vals:
                line.write({'price_unit': vals['price_unit']})
            if 'quantity' in vals:
                self._update_received_qty(line, vals['quantity'])
            updated += 1

        return updated

    def _update_received_qty(self, order_line, quantity):
        """Met à jour la quantité reçue dans le bon de réception ouvert."""
        pickings = order_line.order_id.picking_ids.filtered(
            lambda p: p.state not in ['done', 'cancel']
        )
        if not pickings:
            return 0

        picking = pickings[0]
        moves   = picking.move_ids.filtered(
            lambda m: m.product_id.id == order_line.product_id.id
            and m.state not in ['done', 'cancel']
        )
        if not moves:
            return 0

        move = moves[0]
        if move.move_line_ids:
            move.move_line_ids[0].write({'quantity': quantity})
        else:
            self.env['stock.move.line'].create({
                'move_id':          move.id,
                'product_id':       move.product_id.id,
                'product_uom_id':   move.product_uom.id,
                'location_id':      move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
                'quantity':         quantity,
                'picking_id':       picking.id,
            })
        return quantity

    # ----------------------------------------------------------
    # GESTION DE LA DATE DU DERNIER IMPORT
    # ----------------------------------------------------------

    def _get_last_import_date(self, company_id):
        """Retourne la date du dernier import réussi (défaut : 7 jours en arrière)."""
        cfg = self.env['ir.config_parameter'].sudo()
        val = cfg.get_param(f'sage_x3.last_import_date.company_{company_id}')
        if val:
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                _logger.warning("⚠️ Date de dernier import corrompue pour société %s.", company_id)
        return datetime.now() - timedelta(days=7)

    def _update_last_import_date(self, company_id):
        """Enregistre la date courante comme dernier import réussi."""
        self.env['ir.config_parameter'].sudo().set_param(
            f'sage_x3.last_import_date.company_{company_id}',
            datetime.now().isoformat(),
        )

    # ----------------------------------------------------------
    # NOTIFICATIONS
    # ----------------------------------------------------------

    @staticmethod
    def _action_notification(title, message, notif_type='info', sticky=False):
        """Retourne une action de notification Odoo standard."""
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   title,
                'message': message,
                'type':    notif_type,
                'sticky':  sticky,
            },
        }

    def _bus_notify(self, title, message, notif_type='info', sticky=False):
        """Envoie une notification bus à l'utilisateur courant."""
        user = self.env.user
        if user and user.partner_id:
            self.env['bus.bus']._sendone(
                user.partner_id,
                'simple_notification',
                {'title': title, 'message': message, 'type': notif_type, 'sticky': sticky},
            )

    def _notify_import_completion(self, stats, duration, company_name):
        """Notification de fin d'import avec statistiques."""
        msg = (
            f"Import terminé en {duration:.1f} s\n"
            f"Société : {company_name}\n\n"
            f"• Total reçus   : {stats['total']}\n"
            f"• Mis à jour    : {stats['updated']}\n"
            f"• Lignes        : {stats['lines']}\n"
            f"• Erreurs       : {stats['errors']}\n"
            f"• Ignorés       : {stats['skipped']}"
        )
        self._bus_notify(
            f"✅ Import SAGE X3 terminé — {company_name}", msg, 'success'
        )

    def _notify_import_error(self, error_msg, company_name):
        """Notification d'erreur d'import."""
        self._bus_notify(
            f"❌ Erreur import SAGE X3 — {company_name}",
            f"Société : {company_name}\n{error_msg}",
            'danger', sticky=True,
        )

    # ----------------------------------------------------------
    # CRON
    # ----------------------------------------------------------

    @api.model
    def cron_import_deliveries(self):
        """
        Cron job d'import planifié.
        Utilise queue_job si disponible, sinon exécution directe.
        """
        _logger.info("🕐 [CRON] Import SAGE X3 déclenché pour %s", self.env.company.name)

        if 'queue.job' in self.env:
            try:
                self.with_delay(
                    description="[CRON] Import SAGE X3",
                    priority=5,
                )._job_import_deliveries()
                _logger.info("✅ [CRON] Job queue_job créé.")
            except Exception as e:
                _logger.error("❌ [CRON] Erreur queue_job (%s) — exécution directe.", e)
                self._job_import_deliveries()
        else:
            _logger.info("📌 [CRON] Exécution directe (queue_job non installé).")
            self._job_import_deliveries()

        return True