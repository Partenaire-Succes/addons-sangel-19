import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from odoo import fields, models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class PurchaseOrderSageX3(models.Model):
    _name    = 'purchase.order'
    _inherit = ['purchase.order', 'sage.x3.mixin']

    # =========================================================================
    # ENVOI DES COMMANDES VERS SAGE X3
    # =========================================================================

    def action_submit_urgent_command(self):
        """Soumet immédiatement une commande urgente."""
        self.ensure_one()
        if self.type_command != 'urgent':
            raise UserError("La commande doit être marquée comme urgente pour cette action.")
        self.action_verify_product()
        return self.action_submit_to_sage_x3()

    def action_submit_all_pending_to_sage_x3(self):
        """Soumet toutes les commandes en attente de la société courante."""
        pending_orders = self.search([
            ('company_id',        '=',  self.env.company.id),
            ('state',             'in', ['sent']),
            ('sage_x3_submitted', '=',  False),
            ('sage_x3_validated', '=',  False),
            ('type_command',      '!=', 'urgent'),
            ('type_supplier',     '!=', 'local'),
        ])

        if not pending_orders:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title':   'Information',
                    'message': 'Aucune commande en attente de soumission à SAGE X3',
                    'type':    'warning',
                    'sticky':  False,
                },
            }

        ok = ko = 0
        errors = []

        for order in pending_orders:
            try:
                order._submit_to_sage_x3()
                if order.sage_x3_validated:
                    order.button_confirm()
                    ok += 1
                else:
                    ko += 1
                    errors.append(f"{order.name} : {order.sage_x3_error or 'Rejetée'}")
            except UserError as e:
                ko += 1
                errors.append(f"{order.name} : {str(e)}")
            except Exception as e:
                ko += 1
                errors.append(f"{order.name} : Erreur inattendue — {str(e)}")

            if (ok + ko) % 10 == 0:
                self.env.cr.commit()

        self.env.cr.commit()

        message = (
            f"Traitement terminé sur {len(pending_orders)} commande(s) :\n\n"
            f"✅ {ok} : Envoyées avec succès \n"
            f"❌ {ko} : Échecs"
        )
        if errors:
            message += "\n\nDétail des erreurs :\n" + "\n".join(f"• {e}" for e in errors)

        notif_type = 'success' if ko == 0 else ('warning' if ok > 0 else 'danger')
        title      = '✅ Envoi terminé' if ko == 0 else f'⚠️ {ok} succès / {ko} échecs'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': notif_type, 'sticky': True},
        }

    def action_submit_to_sage_x3(self):
        """Soumet la commande courante à SAGE X3."""
        self.ensure_one()

        if self.state not in ['draft']:
            raise UserError("Seules les commandes en brouillon peuvent être soumises")
        if self.sage_x3_validated:
            raise UserError("Déjà validée par SAGE X3")

        try:
            self._submit_to_sage_x3()
            if self.sage_x3_validated:
                self.button_confirm()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title':   '✅ Succès' if self.sage_x3_validated else '⚠️ Attention',
                    'message': self.sage_x3_response_message or self.sage_x3_error or 'Traité',
                    'type':    'success' if self.sage_x3_validated else 'warning',
                },
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '❌ Erreur', 'message': str(e),
                    'type': 'danger', 'sticky': True,
                },
            }

    def _submit_to_sage_x3(self):
        """Prépare et envoie la commande à SAGE X3."""
        self.ensure_one()

        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Échec de l'authentification SAGE X3")

        config     = self._get_sage_x3_config()
        orders_url = f"{config['base_url']}/api/Orders/batch"
        order_data     = self._prepare_order_for_sage_x3()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

        response_data = self._safe_post(orders_url, headers, order_data).json()

        if isinstance(response_data, list) and response_data:
            result  = response_data[0]
            success = result.get("success", False)
            message = result.get("message", "")

            self.write({
                'sage_x3_submitted':        True,
                'sage_x3_validated':        success,
                'sage_x3_submitted_date':   fields.Datetime.now(),
                'sage_x3_response_message': message if success else False,
                'sage_x3_error':            False if success else message,
            })

            self.message_post(
                body=f"{'✅ Validée' if success else '❌ Rejetée'}\n{message}",
                subject=f"{'✅' if success else '❌'} SAGE X3",
            )

            if not success:
                raise UserError(f"Commande rejetée par SAGE X3 : {message}")
            return True

        raise UserError("Réponse inattendue de SAGE X3 (liste vide ou format invalide)")

    def _prepare_order_for_sage_x3(self):
        """Formate la commande pour l'API SAGE X3."""
        self.ensure_one()

        if not self.partner_id or not self.order_line:
            raise UserError("Fournisseur et lignes de commande obligatoires")

        items = []
        for idx, line in enumerate(self.order_line, start=1):
            if not line.product_id.default_code:
                raise UserError(f"Produit sans référence interne : {line.product_id.name}")
            items.append({
                "ligne":      idx * 1000,
                "article":    line.product_id.default_code,
                "TexteLigne": line.name or line.product_id.name or "",
                "quantite":   max(line.product_qty, 0.01),
            })

        return {
            "commandes": [{
                "NumeroCommande":          self.name,
                "siteVente":               "VRIDI",
                "DateCommande":            (self.date_order or datetime.now()).isoformat(),
                "Client":                  self.company_id.lib_company or "YOP01",
                "Devise":                  self.currency_id.name or "XOF",
                "Magasin":                 self.company_id.name or "PRINCIPAL",
                "ReferenceCommandeClient": self.name,
                "items":                   items,
            }]
        }

    # =========================================================================
    # IMPORT DES LIVRAISONS DEPUIS SAGE X3
    # =========================================================================


    def action_import_all_receive_external_source(self):
        """Mise à jour en masse des commandes avec leurs livraisons SAGE X3."""
        purchases = self.search([
            ('company_id',                '=',  self.env.company.id),
            ('state',                     'in', ['purchase']),
            ('sage_x3_submitted',         '=',  True),
            ('sage_x3_validated',         '=',  True),
            ('sage_x3_delivery_received', '=',  False),
        ])

        if not purchases:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title':   'Information',
                    'message': 'Aucune commande en attente de mise à jour de livraisons',
                    'type':    'warning',
                    'sticky':  False,
                },
            }

        success_count = error_count = 0
        errors = []

        for idx, purchase in enumerate(purchases, 1):
            try:
                purchase._job_import_deliveries()
                success_count += 1
                if idx % 10 == 0:
                    self.env.cr.commit()
            except Exception as e:
                error_count += 1
                errors.append(f"{purchase.name}: {str(e)}")

        self.env.cr.commit()
        message = (
            f"Traitement terminé sur {len(purchases)} commande(s)\n\n"
            f"✅ {success_count} : Succès\n"
            f"❌ {error_count} : Erreurs"
        )

        if errors:
            message += "\n\nDétails :\n" + "\n".join(errors[:10])  # limite à 10

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Import livraisons SAGE X3',
                'message': message,
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': True,
            }
        }

    # =========================================================================
    # JOB PRINCIPAL D'IMPORT
    # =========================================================================

    def _job_import_deliveries(self):
        """
        Job principal : récupère les livraisons SAGE X3, filtre par société,
        et met à jour les commandes et pickings correspondants.
        """
        start_time      = datetime.now()
        current_company = self.env.company

        try:
            token = self._authenticate_sage_x3()
            if not token:
                raise UserError("Échec de l'authentification SAGE X3")

            config      = self._get_sage_x3_config()
            receive_url = f"{config['base_url']}/api/Orders/deliveries"
            headers        = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

            last_import = self._get_last_import_date(current_company.id)
            params      = {'since': last_import.isoformat()} if last_import else None

            _logger.info("📡 Récupération des livraisons depuis %s", last_import or "début")
            response = self._safe_get(receive_url, headers, params=params)

            if response.status_code != 200:
                raise UserError(f"Erreur API : {response.status_code}")

            deliveries = self._parse_deliveries_response(response.text)

            if not deliveries:
                _logger.info("✅ Aucune livraison à traiter pour %s", current_company.name)
                return {'updated': 0, 'errors': 0}

            deliveries_filtered = self._filter_deliveries_by_company(deliveries, current_company)

            if not deliveries_filtered:
                _logger.info("✅ Aucune livraison pour %s", current_company.name)
                return {'updated': 0, 'errors': 0}

            _logger.info("📦 %s livraison(s) à traiter pour %s",
                         len(deliveries_filtered), current_company.name)

            order_cache, product_cache = self._preload_data(
                deliveries_filtered, current_company.id
            )

            stats = self._process_deliveries_in_batches(
                deliveries_filtered, order_cache, product_cache, current_company.id
            )

            self._update_last_import_date(current_company.id)

            duration = (datetime.now() - start_time).total_seconds()
            self._notify_import_completion(stats, duration, current_company.name)

            return stats

        except Exception as e:
            _logger.exception("❌ [JOB] Erreur fatale pour %s : %s", current_company.name, str(e))
            self._notify_import_error(str(e), current_company.name)
            raise

    # =========================================================================
    # FILTRAGE ET PARSING
    # =========================================================================

    def _filter_deliveries_by_company(self, deliveries, company):
        if not deliveries:
            return []

        all_refs = [
            str(d.get("referenceCommandeClient", "")).strip()
            for d in deliveries
            if d.get("referenceCommandeClient")
        ]
        if not all_refs:
            return []

        company_orders = self.search([
            ('name',                      'in',  all_refs),
            ('company_id',                '=',   company.id),
            ('sage_x3_submitted',         '=',   True),
            ('sage_x3_validated',         '=',   True),
            ('sage_x3_delivery_received', '=',   False),
        ])

        valid_refs = set(company_orders.mapped('name'))
        filtered   = [
            d for d in deliveries
            if str(d.get("referenceCommandeClient", "")).strip() in valid_refs
        ]

        _logger.info("🔍 Filtrage '%s' : %s/%s livraisons retenues",
                     company.name, len(filtered), len(deliveries))
        return filtered

    def _parse_deliveries_response(self, response_text):
        """Parse la réponse JSON et retourne la liste aplatie des livraisons."""
        try:
            if len(response_text) > 10_000_000:
                _logger.info("⚠️ JSON volumineux (%.1f MB)", len(response_text) / 1_000_000)

            raw        = json.loads(response_text)
            deliveries = []

            if isinstance(raw, dict) and "livraison" in raw:
                for items_list in raw["livraison"].values():
                    if isinstance(items_list, list):
                        deliveries.extend(items_list)

            deliveries.sort(key=lambda x: x.get('dateCommande', ''), reverse=True)
            return deliveries

        except json.JSONDecodeError as e:
            _logger.error("❌ JSON invalide : %s", str(e))
            return []

    # =========================================================================
    # PRÉ-CHARGEMENT ET TRAITEMENT PAR LOTS
    # =========================================================================

    def _preload_data(self, deliveries, company_id):
        """Pré-charge commandes et produits en un minimum de requêtes (anti N+1)."""
        order_refs = list({
            str(d.get("referenceCommandeClient", "")).strip()
            for d in deliveries
            if d.get("referenceCommandeClient")
        })

        if not order_refs:
            return {}, {}

        orders = self.search([
            ('name',                      'in',  order_refs),
            ('company_id',                '=',   company_id),
            ('sage_x3_submitted',         '=',   True),
            ('sage_x3_validated',         '=',   True),
            ('sage_x3_delivery_received', '=',   False),
            ('state',                     'in',  ['purchase']),
        ])
        order_cache = {o.name: o.id for o in orders}

        all_articles = {
            item.get("article")
            for d in deliveries
            for item in d.get("items", [])
            if item.get("article")
        }

        products     = self.env['product.product'].search(
            [('default_code', 'in', list(all_articles))]
        )
        product_cache = {p.default_code: p.id for p in products}

        _logger.info("✅ Caches : %s commandes, %s produits",
                     len(order_cache), len(product_cache))
        return order_cache, product_cache

    def _process_deliveries_in_batches(self, deliveries, order_cache, product_cache, company_id):
        """Traitement par lots avec commits intermédiaires."""
        total   = len(deliveries)
        updated = errors = lines = skipped = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total)
            batch     = deliveries[batch_start:batch_end]

            _logger.info("🔄 Lot %s–%s / %s (%.1f%%)",
                         batch_start + 1, batch_end, total, batch_end / total * 100)

            stats    = self._process_batch(batch, batch_start, order_cache, product_cache)
            updated += stats['updated']
            lines   += stats['lines']
            errors  += stats['errors']
            skipped += stats['skipped']

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
        """Traite un lot de livraisons."""
        stats = {'updated': 0, 'lines': 0, 'errors': 0, 'skipped': 0}

        for i, delivery in enumerate(batch, start=offset + 1):
            try:
                if not isinstance(delivery, dict):
                    stats['errors'] += 1
                    continue

                ref = str(delivery.get("referenceCommandeClient", "")).strip()
                ref_sage = str(delivery.get("numeroCommande", "")).strip()
                if not ref:
                    stats['skipped'] += 1
                    continue

                order_id = order_cache.get(ref)
                if not order_id:
                    stats['skipped'] += 1
                    continue

                order        = self.browse(order_id)
                lines_count  = self._update_order_lines_optimized(
                    order, delivery.get("items", []), product_cache, ref_sage
                )
                stats['lines'] += lines_count

                order.write({
                    'sage_x3_delivery_received': True,
                    'sage_x3_delivery_date':     fields.Datetime.now(),
                    'partner_ref':               ref_sage,
                })
                stats['updated'] += 1

            except Exception as e:
                _logger.error("❌ Erreur livraison #%s : %s", i, str(e))
                stats['errors'] += 1

        return stats

    def _update_order_lines_optimized(self, order, items, product_cache, ref_sage):
        """Met à jour les lignes de commande (prix et quantités) depuis les items SAGE X3."""
        if not items:
            return 0

        updates      = defaultdict(dict)
        lines_updated = 0

        for item in items:
            article_code = item.get("article")
            if not article_code:
                continue

            product_id = product_cache.get(article_code)
            if not product_id:
                continue

            order_lines = order.order_line.filtered(
                lambda l: l.product_id.id == product_id
            )
            if not order_lines:
                continue

            order_line = order_lines[0]
            quantity   = item.get("quantite")
            unit_price = item.get("prix")

            if unit_price is not None and unit_price != order_line.price_unit:
                updates[order_line.id]['price_unit'] = unit_price
            if quantity is not None and quantity > 0:
                updates[order_line.id]['quantity'] = quantity

        for line_id, values in updates.items():
            line = self.env['purchase.order.line'].browse(line_id)
            write_vals = {}
            if 'price_unit' in values:
                write_vals['price_unit'] = values['price_unit']
            if write_vals:
                line.write(write_vals)
            if 'quantity' in values:
                self._update_quantity_received_picking(line, values['quantity'], ref_sage)
            lines_updated += 1

        return lines_updated

    def _update_quantity_received_picking(self, order_line, quantity, ref_sage):
        """Met à jour la quantité dans le picking lié à la ligne de commande."""
        picking = order_line.order_id.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel')
        )
        if not picking:
            return 0

        picking = picking[0]
        picking.write({
            'ref_sage': ref_sage,
            'date_sage': fields.Datetime.now(),
        })
        move    = picking.move_ids.filtered(
            lambda m: m.product_id.id == order_line.product_id.id
                      and m.state not in ('done', 'cancel')
        )
        if not move:
            return 0

        move = move[0]

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

    # =========================================================================
    # GESTION DE LA DATE DE DERNIER IMPORT
    # =========================================================================

    def _get_last_import_date(self, company_id):
        value = self.env['ir.config_parameter'].sudo().get_param(
            f'sage_x3.last_import_date.company_{company_id}'
        )
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                pass
        return datetime.now() - timedelta(days=7)

    def _update_last_import_date(self, company_id):
        self.env['ir.config_parameter'].sudo().set_param(
            f'sage_x3.last_import_date.company_{company_id}',
            datetime.now().isoformat(),
        )

    # =========================================================================
    # NOTIFICATIONS BUS
    # =========================================================================

    def _notify_import_completion(self, stats, duration, company_name):
        user = self.env.user
        if not user:
            return
        message = (
            f"✅ Import terminé en {duration:.1f}s\n"
            f"🏢 Société : {company_name}\n\n"
            f"• Total       : {stats['total']}\n"
            f"• Mises à jour: {stats['updated']}\n"
            f"• Lignes      : {stats['lines']}\n"
            f"• Erreurs     : {stats['errors']}\n"
            f"• Ignorées    : {stats['skipped']}"
        )
        self.env['bus.bus']._sendone(
            user.partner_id,
            'simple_notification',
            {'title': f'✅ Import SAGE X3 — {company_name}',
             'message': message, 'type': 'success'},
        )

    def _notify_import_error(self, error_msg, company_name):
        user = self.env.user
        if not user:
            return
        self.env['bus.bus']._sendone(
            user.partner_id,
            'simple_notification',
            {'title': f'❌ Erreur import SAGE X3 — {company_name}',
             'message': f"Société : {company_name}\n{error_msg}",
             'type': 'danger', 'sticky': True},
        )

    # =========================================================================
    # CRON
    # =========================================================================

    @api.model
    def cron_import_deliveries(self):
        """Cron planifié : utilise queue_job si disponible, sinon exécution directe."""
        _logger.info("🕐 [CRON] Import livraisons SAGE X3 planifié")

        if 'queue.job' in self.env:
            try:
                self.with_delay(
                    description="[CRON] Import SAGE X3",
                    priority=5,
                )._job_import_deliveries()
                _logger.info("✅ [CRON] Job queue_job créé")
                return True
            except Exception as e:
                _logger.error("❌ [CRON] Erreur queue_job : %s — exécution directe", str(e))

        _logger.info("📌 [CRON] Exécution directe (queue_job absent)")
        self._job_import_deliveries()
        return True
