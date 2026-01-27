import requests
import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError
import json
from datetime import datetime, timedelta
from collections import defaultdict

_logger = logging.getLogger(__name__)

BASE_URL = "http://172.16.2.150:8030"
AUTH_URL = f"{BASE_URL}/api/Auth/login"
ORDERS_SEND_URL = f"{BASE_URL}/api/Orders/batch"
ORDERS_RECEIVE_URL = f"{BASE_URL}/api/Orders/deliveries"
USERNAME = "odoo"
PASSWORD = "InterfaceX3_Odoo"

TIMEOUT = 30
MAX_RETRIES = 3
BATCH_SIZE = 10  # Augmenté à 10 pour meilleures performances
CACHE_TIMEOUT = 3600  # Cache d'1 heure


class PurchaseOrderSageX3Optimized(models.Model):
    _inherit = "purchase.order"

    def action_submit_urgent_command(self):
        """Soummetre une commande urgente immédiatement"""
        self.ensure_one()
        if self.type_command == 'urgent':
            return self.action_submit_to_sage_x3()
        else:
            raise UserError("La commande doit être marquée comme urgente pour cette action.")
    def action_submit_to_sage_x3(self):
        """Soumettre la commande à SAGE X3"""
        self.ensure_one()
        
        if self.state not in ['draft', 'sent']:
            raise UserError("Seules les commandes en brouillon peuvent être soumises")
        
        if self.sage_x3_validated:
            raise UserError("Déjà validée par SAGE X3")
        
        try:
            self.submit_to_sage_x3()

            if self.sage_x3_validated:
                self.button_confirm()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Succès' if self.sage_x3_validated else '⚠️ Attention',
                    'message': self.sage_x3_response_message or self.sage_x3_error or 'Traité',
                    'type': 'success' if self.sage_x3_validated else 'warning',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '❌ Erreur',
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def submit_to_sage_x3(self):
        """Soumet à SAGE X3"""
        self.ensure_one()
        
        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec authentification")
        
        order_data = self._prepare_order_for_sage_x3()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = self._safe_post(ORDERS_SEND_URL, headers, order_data)
        
        if response.status_code in (200, 201):
            response_data = response.json()
            
            if isinstance(response_data, list) and response_data:
                result = response_data[0]
                success = result.get("success", False)
                message = result.get("message", "")
                
                self.write({
                    'sage_x3_submitted': True,
                    'sage_x3_validated': success,
                    'sage_x3_submitted_date': fields.Datetime.now(),
                    'sage_x3_response_message': message if success else False,
                    'sage_x3_error': False if success else message,
                })
                
                self.message_post(
                    body=f"<h3>{'✅ Validée' if success else '❌ Rejetée'}</h3><p>{message}</p>",
                    subject=f"{'✅' if success else '❌'} SAGE X3"
                )
                
                if not success:
                    raise UserError(f"Rejetée: {message}")
                return True
        
        raise UserError(f"Erreur HTTP {response.status_code}")

    def _authenticate_sage_x3(self):
        """Auth SAGE X3"""
        try:
            response = requests.post(
                AUTH_URL, 
                json={"username": USERNAME, "password": PASSWORD}, 
                timeout=15
            )
            return response.json().get("token") if response.status_code in (200, 201) else None
        except:
            return None

    def _safe_post(self, url, headers, data, timeout=TIMEOUT):
        """POST avec retry"""
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                if response.status_code in (200, 201):
                    return response
            except:
                pass
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(2)
        return requests.post(url, headers=headers, json=data, timeout=timeout)

    def _safe_get(self, url, headers, params=None, timeout=TIMEOUT):
        """GET avec retry"""
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                if response.status_code == 200:
                    return response
            except:
                pass
            if attempt < MAX_RETRIES - 1:
                import time
                time.sleep(2)
        return requests.get(url, headers=headers, params=params, timeout=timeout)

    def _prepare_order_for_sage_x3(self):
        """Prépare pour SAGE X3"""
        self.ensure_one()
        
        if not self.partner_id or not self.order_line:
            raise UserError("Fournisseur et lignes obligatoires")
        
        items = []
        for idx, line in enumerate(self.order_line, start=1):
            if not line.product_id.default_code:
                raise UserError(f"Produit sans référence: {line.product_id.name}")
            
            items.append({
                "ligne": idx * 1000,
                "article": line.product_id.default_code,
                "TexteLigne": line.name or line.product_id.name or "",
                "quantite": max(line.product_qty, 0.01)
            })
        
        return {
            "commandes": [{
                "siteVente": "VRIDI",
                "DateCommande": (self.date_order or datetime.now()).isoformat(),
                "Client": self.company_id.code_company or "01",
                "Devise": self.currency_id.name or "XOF",
                "Magasin": self.company_id.name or "PRINCIPAL",
                "ReferenceCommandeClient": self.name,
                "items": items
            }]
        }

    # ========================================================================
    # IMPORT OPTIMISÉ AVEC QUEUE_JOB
    # ========================================================================

    @api.model
    def action_import_deliveries(self):
        """Lance l'import asynchrone via queue_job"""
        # Vérifier si un job est déjà en cours
        existing_jobs = self.env['queue.job'].search([
            ('name', 'ilike', 'Import livraisons SAGE X3'),
            ('state', 'in', ['pending', 'enqueued', 'started']),
        ])
        
        if existing_jobs:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '⚠️ Import en cours',
                    'message': 'Un import est déjà en cours d\'exécution',
                    'type': 'warning',
                }
            }
        
        # Lancer le job avec haute priorité
        self.with_delay(
            description="Import livraisons SAGE X3",
            priority=10,  # Haute priorité
            max_retries=2,
            eta=datetime.now() + timedelta(seconds=5)  # Démarrer dans 5 secondes
        )._job_import_deliveries()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '🚀 Import planifié',
                'message': 'L\'import démarrera dans 5 secondes. Consultez les jobs dans Paramètres > Queue Jobs.',
                'type': 'info',
            }
        }

    @api.model
    def _job_import_deliveries(self):
        """
        Job principal d'import
        Cette méthode est exécutée par queue_job dans un worker séparé
        """
        start_time = datetime.now()
        _logger.info("="*80)
        _logger.info("🚀 [JOB] Démarrage import SAGE X3 - %s", start_time)
        _logger.info("="*80)
        
        try:
            # 1. Authentification
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec authentification")
            
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            
            # 2. Import incrémental (seulement les nouvelles depuis le dernier import)
            last_import = self._get_last_import_date()
            params = {'since': last_import.isoformat()} if last_import else None
            
            # 3. Récupération des livraisons
            _logger.info("📡 Récupération des livraisons depuis %s", last_import or "début")
            response = self._safe_get(ORDERS_RECEIVE_URL, headers, params=params)
            
            if response.status_code != 200:
                raise UserError(f"Erreur API: {response.status_code}")
            
            # 4. Parse JSON avec gestion mémoire
            deliveries = self._parse_deliveries_response(response.text)
            
            if not deliveries:
                _logger.info("✅ Aucune livraison à traiter")
                return {'updated': 0, 'errors': 0}
            
            _logger.info("📦 %s livraisons à traiter", len(deliveries))
            
            # 5. Pré-chargement des données pour optimiser
            self._preload_data(deliveries)
            
            # 6. Traitement par lots avec commits intermédiaires
            stats = self._process_deliveries_in_batches(deliveries)
            
            # 7. Mise à jour de la date du dernier import
            self._update_last_import_date()
            
            # 8. Statistiques finales
            duration = (datetime.now() - start_time).total_seconds()
            _logger.info("="*80)
            _logger.info("✅ [JOB] Import terminé en %.2f secondes", duration)
            _logger.info("📊 Stats: %s", stats)
            _logger.info("="*80)
            
            # 9. Notification utilisateur
            self._notify_import_completion(stats, duration)
            
            return stats
            
        except Exception as e:
            _logger.exception("❌ [JOB] Erreur fatale: %s", str(e))
            self._notify_import_error(str(e))
            raise

    def _parse_deliveries_response(self, response_text):
        """
        Parse le JSON de manière optimisée pour éviter les problèmes de mémoire
        """
        try:
            # Parse incrémental si très gros JSON
            if len(response_text) > 10_000_000:  # > 10MB
                _logger.info("⚠️ JSON volumineux (%s MB), parsing optimisé", len(response_text) / 1_000_000)
            
            raw = json.loads(response_text)
            
            # Extraction des livraisons
            deliveries = []
            if isinstance(raw, dict) and "livraison" in raw:
                for date_key, items_list in raw["livraison"].items():
                    if isinstance(items_list, list):
                        deliveries.extend(items_list)
            
            # Tri par date pour traiter les plus récentes en premier
            deliveries.sort(key=lambda x: x.get('dateCommande', ''), reverse=True)
            
            return deliveries
            
        except json.JSONDecodeError as e:
            _logger.error("❌ JSON invalide: %s", str(e))
            return []

    def _preload_data(self, deliveries):
        """
        Pré-charge toutes les données nécessaires en une seule requête
        pour éviter les N+1 queries
        """
        # Extraire toutes les références de commandes
        order_refs = list(set(
            str(d.get("referenceCommandeClient", "")).strip() 
            for d in deliveries 
            if d.get("referenceCommandeClient")
        ))
        
        if not order_refs:
            return
        
        _logger.info("🔄 Pré-chargement de %s commandes", len(order_refs))
        
        # Charger toutes les commandes en une seule requête
        orders = self.search([
            ('name', 'in', order_refs),
            ('sage_x3_submitted', '=', True),
            ('sage_x3_validated', '=', True),
            ('state', 'in', ['purchase', 'to approve'])
        ])
        
        # Créer un cache en mémoire {ref: order_id}
        self._order_cache = {order.name: order.id for order in orders}
        
        # Pré-charger tous les produits utilisés
        all_articles = set()
        for d in deliveries:
            for item in d.get("items", []):
                article = item.get("article")
                if article:
                    all_articles.add(article)
        
        _logger.info("🔄 Pré-chargement de %s produits", len(all_articles))
        
        products = self.env['product.product'].search([
            ('default_code', 'in', list(all_articles))
        ])
        
        # Cache {default_code: product_id}
        self._product_cache = {p.default_code: p.id for p in products}
        
        _logger.info("✅ Caches initialisés")

    def _process_deliveries_in_batches(self, deliveries):
        """Traitement par lots avec commits intermédiaires"""
        total = len(deliveries)
        updated = errors = lines = skipped = 0
        
        for batch_start in range(0, total, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total)
            batch = deliveries[batch_start:batch_end]
            
            progress = (batch_end / total) * 100
            _logger.info("🔄 Lot %s-%s/%s (%.1f%%)", batch_start + 1, batch_end, total, progress)
            
            # Traiter le lot
            batch_stats = self._process_batch(batch, batch_start)
            
            updated += batch_stats['updated']
            lines += batch_stats['lines']
            errors += batch_stats['errors']
            skipped += batch_stats['skipped']
            
            # Commit intermédiaire toutes les N commandes
            self.env.cr.commit()
            
            # Libérer la mémoire
            self.env.clear()
        
        return {
            'total': total,
            'updated': updated,
            'lines': lines,
            'errors': errors,
            'skipped': skipped
        }

    def _process_batch(self, batch, offset):
        """Traite un lot de livraisons"""
        stats = {'updated': 0, 'lines': 0, 'errors': 0, 'skipped': 0}
        
        for i, delivery in enumerate(batch, start=offset + 1):
            try:
                if not isinstance(delivery, dict):
                    stats['errors'] += 1
                    continue
                
                ref = str(delivery.get("referenceCommandeClient", "")).strip()
                
                if not ref or ref == " ":
                    stats['skipped'] += 1
                    continue
                
                # Utiliser le cache au lieu d'une recherche DB
                order_id = self._order_cache.get(ref)
                if not order_id:
                    stats['skipped'] += 1
                    continue
                
                order = self.browse(order_id)
                
                # Mise à jour des lignes
                lines_count = self._update_order_lines_optimized(order, delivery.get("items", []))
                stats['lines'] += lines_count
                
                # Mise à jour de la commande
                partner_ref = str(delivery.get("numeroCommande", "")).strip()
                order.write({
                    'sage_x3_delivery_received': True,
                    'sage_x3_delivery_date': fields.Datetime.now(),
                    'partner_ref': partner_ref
                })
                
                stats['updated'] += 1
                
                if i % 10 == 0:  # Log tous les 10
                    _logger.info("✅ Traité: %s/%s", i, len(batch) + offset)
                
            except Exception as e:
                _logger.error("❌ Erreur livraison #%s: %s", i, str(e))
                stats['errors'] += 1
        
        return stats

    def _update_order_lines_optimized(self, order, items):
        """Mise à jour optimisée des lignes"""
        if not items:
            return 0
        
        lines_updated = 0
        
        # Grouper les mises à jour par ligne
        updates = defaultdict(dict)
        
        for item in items:
            article_code = item.get("article")
            if not article_code:
                continue
            
            # Utiliser le cache produit
            product_id = self._product_cache.get(article_code)
            if not product_id:
                continue
            
            # Trouver la ligne
            order_line = order.order_line.filtered(
                lambda l: l.product_id.id == product_id
            )
            
            if not order_line:
                continue
            
            order_line = order_line[0]
            
            # Préparer les mises à jour
            quantity = item.get("quantite")
            unit_price = item.get("prix")
            
            if unit_price is not None and unit_price != order_line.price_unit:
                updates[order_line.id]['price_unit'] = unit_price
            
            if quantity is not None and quantity > 0:
                updates[order_line.id]['quantity'] = quantity
        
        # Appliquer toutes les mises à jour en une fois
        for line_id, values in updates.items():
            line = self.env['purchase.order.line'].browse(line_id)
            
            if 'price_unit' in values:
                line.write({'price_unit': values['price_unit']})
            
            if 'quantity' in values:
                self._update_quantity_received_picking(line, values['quantity'])
            
            lines_updated += 1
        
        return lines_updated

    def _update_quantity_received_picking(self, order_line, quantity):
        """MAJ picking optimisée"""
        picking = order_line.order_id.picking_ids.filtered(
            lambda p: p.state not in ['done', 'cancel']
        )
        
        if not picking:
            return 0
        
        picking = picking[0]
        
        move = picking.move_ids.filtered(
            lambda m: m.product_id.id == order_line.product_id.id 
            and m.state not in ['done', 'cancel']
        )
        
        if not move:
            return 0
        
        move = move[0]
        
        if move.move_line_ids:
            move.move_line_ids[0].write({'quantity': quantity})
        else:
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'product_id': move.product_id.id,
                'product_uom_id': move.product_uom.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
                'quantity': quantity,
                'picking_id': picking.id,
            })
        
        return quantity

    def _get_last_import_date(self):
        """Récupère la date du dernier import réussi"""
        config = self.env['ir.config_parameter'].sudo()
        last_import_str = config.get_param('sage_x3.last_import_date')
        
        if last_import_str:
            try:
                return datetime.fromisoformat(last_import_str)
            except:
                pass
        
        # Par défaut: 7 jours en arrière
        return datetime.now() - timedelta(days=7)

    def _update_last_import_date(self):
        """Met à jour la date du dernier import"""
        config = self.env['ir.config_parameter'].sudo()
        config.set_param('sage_x3.last_import_date', datetime.now().isoformat())

    def _notify_import_completion(self, stats, duration):
        """Notification de fin"""
        message = f"""
        ✅ Import terminé en {duration:.1f}s
        
        • Total: {stats['total']}
        • Mises à jour: {stats['updated']}
        • Lignes: {stats['lines']}
        • Erreurs: {stats['errors']}
        • Ignorées: {stats['skipped']}
        """
        
        # Notifier les managers
        group = self.env.ref('purchase.group_purchase_manager', raise_if_not_found=False)
        if group:
            for user in group.users:
                self.env['bus.bus']._sendone(
                    user.partner_id,
                    'simple_notification',
                    {
                        'title': '✅ Import SAGE X3 terminé',
                        'message': message,
                        'type': 'success',
                    }
                )

    def _notify_import_error(self, error_msg):
        """Notification d'erreur"""
        group = self.env.ref('purchase.group_purchase_manager', raise_if_not_found=False)
        if group:
            for user in group.users:
                self.env['bus.bus']._sendone(
                    user.partner_id,
                    'simple_notification',
                    {
                        'title': '❌ Erreur import SAGE X3',
                        'message': error_msg,
                        'type': 'danger',
                        'sticky': True,
                    }
                )

    @api.model
    def cron_import_deliveries(self):
        """Cron job"""
        _logger.info("🕐 [CRON] Import planifié")
        self.with_delay(
            description="[CRON] Import SAGE X3",
            priority=5
        )._job_import_deliveries()
        return True