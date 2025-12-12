from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _create_order_picking(self):
        """Override pour gérer la synchronisation carton/unité après création des pickings"""
        res = super()._create_order_picking()

        # Traiter la synchronisation carton après création du picking
        for order in self:
            for line in order.lines:
                if line.qty > 0:  # Seulement pour les ventes (pas les retours)
                    line._process_pack_synchronization()

        return res


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    def _process_pack_synchronization(self):
        """Traite la synchronisation pack/unité pour cette ligne de commande"""
        if not self.product_id or self.qty <= 0:
            return

        # Cas 1: Vente d'unités → décrémenter cartons quand complet
        pack_template = self._get_pack_parent()
        if pack_template:
            self._update_pack_counter(pack_template)
            return

        # Cas 2: Vente de cartons → décrémenter unités correspondantes
        carton_template = self._get_carton_template()
        if carton_template:
            self._decrement_units_for_carton_sale(carton_template)

    def _get_pack_parent(self):
        """Trouve le template pack parent pour ce produit (si c'est une unité)"""
        pack_template = self.env['product.template'].search([
            ('is_pack_parent', '=', True),
            ('pack_child_product_id', '=', self.product_id.id)
        ], limit=1)

        if not pack_template or pack_template.pack_qty <= 0:
            _logger.debug(f"[PACK SYNC] Aucun carton parent trouvé pour {self.product_id.name}")
            return False

        return pack_template

    def _get_carton_template(self):
        """Vérifie si ce produit est un carton (template pack parent)"""
        template = self.product_id.product_tmpl_id

        if (hasattr(template, 'is_pack_parent') and
                template.is_pack_parent and
                template.pack_child_product_id and
                template.pack_qty > 0):
            return template

        _logger.debug(f"[PACK SYNC] {self.product_id.name} n'est pas un carton")
        return False

    def _update_pack_counter(self, pack_template):
        """Met à jour le compteur d'unités et traite les cartons complets"""
        _logger.info(
            f"[PACK SYNC UNITÉS] Produit: {self.product_id.name}, Carton: {pack_template.name}, Qty: {self.qty}")

        # Mettre à jour le compteur d'unités vendues
        new_pending = pack_template.pending_units + self.qty
        pack_template.write({'pending_units': new_pending})

        # Calculer le nombre de cartons complets à décrémenter
        full_cartons = int(new_pending // pack_template.pack_qty)

        if full_cartons <= 0:
            _logger.info(f"[PACK SYNC UNITÉS] Cumul insuffisant: {new_pending}/{pack_template.pack_qty}")
            return

        # Mettre à jour les unités restantes
        remaining_units = new_pending - (full_cartons * pack_template.pack_qty)
        pack_template.write({'pending_units': remaining_units})

        # Décrémenter le stock du carton
        self._decrement_pack_stock(pack_template, full_cartons)

        _logger.info(
            f"[PACK SYNC UNITÉS] RÉSULTAT: {self.qty} unités vendues → {full_cartons} cartons décrémentés, {remaining_units} unités restantes")

    def _decrement_units_for_carton_sale(self, carton_template):
        """Décrémente le stock des unités quand on vend des cartons"""
        units_to_remove = self.qty * carton_template.pack_qty
        child_product = carton_template.pack_child_product_id

        _logger.info(
            f"[PACK SYNC CARTONS] Vente de {self.qty} cartons → décrément de {units_to_remove} unités {child_product.name}")

        # Obtenir l'emplacement stock
        stock_location = self._get_stock_location()
        if not stock_location:
            return

        try:
            # Décrémenter le stock des unités
            self.env['stock.quant']._update_available_quantity(
                child_product,
                stock_location,
                -units_to_remove,  # Quantité négative = sortie
                package_id=False,
                lot_id=False,
                owner_id=False
            )

            # Invalider le cache pour forcer le recalcul
            child_product.invalidate_recordset(['qty_available'])

            _logger.info(f"[PACK SYNC CARTONS] Stock unités mis à jour. Nouveau stock: {child_product.qty_available}")

        except Exception as e:
            _logger.error(f"[PACK SYNC CARTONS] Erreur lors de la mise à jour du stock des unités: {str(e)}")
            # En cas d'erreur, essayer avec un mouvement de stock
            self._create_stock_move_fallback(child_product, stock_location, units_to_remove)

    def _decrement_pack_stock(self, pack_template, cartons_qty):
        """Décrémente le stock du produit carton"""
        carton_product = pack_template.product_variant_id
        if not carton_product:
            _logger.error(f"[PACK SYNC UNITÉS] Pas de variante pour {pack_template.name}")
            return

        # Obtenir l'emplacement stock
        stock_location = self._get_stock_location()
        if not stock_location:
            return

        _logger.info(f"[PACK SYNC UNITÉS] Décrément de {cartons_qty} cartons pour {carton_product.name}")

        try:
            # Méthode principale: utiliser _update_available_quantity
            self.env['stock.quant']._update_available_quantity(
                carton_product,
                stock_location,
                -cartons_qty,  # Quantité négative = sortie
                package_id=False,
                lot_id=False,
                owner_id=False
            )

            # Invalider le cache pour forcer le recalcul
            carton_product.invalidate_recordset(['qty_available'])

            _logger.info(
                f"[PACK SYNC UNITÉS] Stock cartons mis à jour avec succès. Nouveau stock: {carton_product.qty_available}")

        except Exception as e:
            _logger.error(f"[PACK SYNC UNITÉS] Erreur lors de la mise à jour du stock: {str(e)}")
            # En cas d'erreur, essayer avec un mouvement de stock
            self._create_stock_move_fallback(carton_product, stock_location, cartons_qty)

    def _get_stock_location(self):
        """Obtient l'emplacement de stock approprié"""
        # Essayer d'abord avec l'entrepôt de la société
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if warehouse and warehouse.lot_stock_id:
            return warehouse.lot_stock_id

        # Fallback sur l'emplacement stock par défaut
        try:
            return self.env.ref('stock.stock_location_stock')
        except:
            _logger.error("[PACK SYNC] Aucun emplacement stock trouvé")
            return False

    def _create_stock_move_fallback(self, product, stock_location, qty):
        """Méthode de fallback utilisant un mouvement de stock"""
        try:
            customer_location = self.env.ref('stock.stock_location_customers')

            move_vals = {
                'name': f'Décrément pack POS - {self.order_id.name}',
                'product_id': product.id,
                'product_uom': product.uom_id.id,
                'product_uom_qty': qty,
                'location_id': stock_location.id,
                'location_dest_id': customer_location.id,
                'origin': f'POS/{self.order_id.name}',
                'company_id': self.company_id.id,
            }

            move = self.env['stock.move'].create(move_vals)
            move._action_confirm()
            move._action_assign()
            move.quantity_done = qty
            move._action_done()

            _logger.info(f"[PACK SYNC] Stock mis à jour via mouvement de stock (fallback) pour {product.name}")

        except Exception as e:
            _logger.error(f"[PACK SYNC] Échec du fallback: {str(e)}")


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        """Override pour déclencher les recalculs après les mouvements POS"""
        res = super()._action_done(cancel_backorder)

        # Traiter les mouvements liés au POS
        pos_moves = self.filtered(lambda m: m.origin and 'POS/' in m.origin)

        if pos_moves:
            # Invalider les caches pour forcer le recalcul des stocks
            products = pos_moves.mapped('product_id')
            products.invalidate_recordset(['qty_available'])

            # Si nécessaire, déclencher d'autres recalculs
            pack_templates = products.mapped('product_tmpl_id').filtered('is_pack_parent')
            if pack_templates and hasattr(pack_templates, '_compute_pack_equivalences'):
                pack_templates._compute_pack_equivalences()

        return res