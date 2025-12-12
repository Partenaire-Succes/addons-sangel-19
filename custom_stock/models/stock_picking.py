from odoo import models, fields, api, _
from odoo.exceptions import UserError
import math
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """Override: synchronisation pack/unités selon les bonnes pratiques Odoo"""
        res = super().button_validate()

        # Réceptions → explosion cartons en unités
        if self.picking_type_code == "incoming":
            self._process_pack_explosion()

        # Livraisons → synchronisation unités vers cartons
        elif self.picking_type_code == "outgoing":
            self._process_unit_to_pack_sync()
            for move in self.move_ids.filtered(lambda m: m.state == "done" and m.product_id):
                pack_template = self._get_pack_template_for_move(move)
                if pack_template:
                    # 👉 décrémenter les unités correspondant aux cartons vendus
                    self._decrement_units_for_sold_cartons(move, pack_template)
        return res

    def _process_pack_explosion(self):
        """
        Traite l'explosion pack → unités selon le pattern Odoo core
        Utilise la même logique que les ajustements d'inventaire
        """
        for move in self.move_ids.filtered(lambda m: m.state == "done" and m.quantity > 0):
            pack_template = self._get_pack_template_for_move(move)
            if not pack_template:
                continue

            # Créer ajustement d'inventaire pour les unités (pattern Odoo standard)
            self._create_inventory_adjustment_for_units(move, pack_template)

    def _process_unit_to_pack_sync(self):
        """
        Traite la synchronisation unités → cartons avec cumul
        Pattern similaire aux kits/bundles d'Odoo
        """
        processed_templates = set()

        for move in self.move_ids.filtered(lambda m: m.state == "done" and m.quantity > 0):
            pack_template = self._get_unit_pack_template(move.product_id)
            if not pack_template or pack_template.id in processed_templates:
                continue

            # Traiter toutes les unités de ce pack d'un coup
            self._process_template_unit_sync(pack_template)
            processed_templates.add(pack_template.id)

    def _get_pack_template_for_move(self, move):
        """Récupère le template pack pour un mouvement de carton"""
        template = move.product_id.product_tmpl_id
        if (hasattr(template, "is_pack_parent") and
                template.is_pack_parent and
                template.pack_child_product_id and
                template.pack_qty > 0):
            return template
        return False

    def _get_unit_pack_template(self, product):
        """Récupère le template pack parent pour un produit unité"""
        return self.env['product.template'].search([
            ("is_pack_parent", "=", True),
            ("pack_child_product_id", "=", product.id),
            ("company_id", "in", [False, self.company_id.id]),
        ], limit=1)

    def _create_inventory_adjustment_for_units(self, carton_move, pack_template):
        """
        Crée un ajustement d'inventaire pour les unités
        Pattern identique au wizard stock.change.product.qty d'Odoo
        """
        child_product = pack_template.pack_child_product_id
        units_qty = carton_move.quantity * pack_template.pack_qty

        try:
            # Utiliser le wizard standard d'Odoo pour l'ajustement
            wizard_vals = {
                'product_id': child_product.id,
                'location_id': carton_move.location_dest_id.id,
                'new_quantity': self._get_current_qty(child_product, carton_move.location_dest_id) + units_qty,
                'product_tmpl_id': child_product.product_tmpl_id.id,
            }

            wizard = self.env['stock.change.product.qty'].create(wizard_vals)
            wizard.change_product_qty()

            _logger.info(f"[PACK_EXPLOSION] {carton_move.quantity} cartons → "
                         f"+{units_qty} unités {child_product.display_name}")

        except Exception as e:
            _logger.error(f"[PACK_EXPLOSION] Erreur ajustement: {str(e)}")
            # Fallback sur méthode directe
            self._direct_inventory_adjustment(child_product, carton_move.location_dest_id, units_qty)

    def _process_template_unit_sync(self, pack_template):
        """
        Traite la synchronisation pour un template pack donné
        Cumule toutes les unités livrées dans ce picking
        """
        child_product = pack_template.pack_child_product_id
        pack_product = pack_template.product_variant_id

        if not pack_product:
            _logger.error(f"[UNIT_SYNC] Pas de variante pour {pack_template.name}")
            return

        # Calculer total unités livrées pour ce produit enfant
        total_units = sum(
            move.quantity for move in self.move_ids
            if move.product_id == child_product and move.state == "done"
        )

        if total_units <= 0:
            return

        # Mettre à jour compteur et traiter cartons complets
        self._update_template_counter_and_process(pack_template, pack_product, total_units)

    def _update_template_counter_and_process(self, pack_template, pack_product, delivered_units):
        """
        Met à jour le compteur d'unités en attente et traite les cartons complets
        """
        current_pending = pack_template.pending_units
        new_pending = current_pending + delivered_units

        # Calculer cartons complets
        full_cartons = int(new_pending // pack_template.pack_qty)
        remaining_units = new_pending % pack_template.pack_qty

        if full_cartons > 0:
            # Ajustement d'inventaire pour les cartons (pattern standard Odoo)
            self._create_inventory_adjustment_for_cartons(pack_product, -full_cartons)

        # Mettre à jour le compteur
        pack_template.write({'pending_units': remaining_units})

        _logger.info(f"[UNIT_SYNC] {delivered_units} unités → "
                     f"{full_cartons} cartons décrémentés, "
                     f"{remaining_units} unités en attente")

    def _create_inventory_adjustment_for_cartons(self, pack_product, carton_adjustment):
        """
        Crée un ajustement d'inventaire pour les cartons
        Utilise le pattern standard d'Odoo (même que Update Qty on Hand)
        """
        try:
            # Obtenir la localisation stock
            stock_location = self._get_main_stock_location()
            if not stock_location:
                raise UserError(_("Impossible de trouver l'emplacement de stock principal"))

            current_qty = self._get_current_qty(pack_product, stock_location)
            new_qty = max(0, current_qty + carton_adjustment)  # Éviter les négatifs

            # Utiliser le wizard standard d'ajustement d'Odoo
            wizard_vals = {
                'product_id': pack_product.id,
                'location_id': stock_location.id,
                'new_quantity': new_qty,
                'product_tmpl_id': pack_product.product_tmpl_id.id,
            }

            wizard = self.env['stock.change.product.qty'].create(wizard_vals)
            wizard.change_product_qty()

            _logger.info(f"[UNIT_SYNC] Ajustement cartons: {carton_adjustment} pour {pack_product.display_name}")

        except Exception as e:
            _logger.error(f"[UNIT_SYNC] Erreur ajustement cartons: {str(e)}")
            # Fallback sur méthode directe
            self._direct_inventory_adjustment(pack_product, stock_location, carton_adjustment)

    def _decrement_units_for_sold_cartons(self, carton_move, pack_template):
        """
        Décrémente les unités correspondantes lors de la vente de cartons
        """
        child_product = pack_template.pack_child_product_id
        units_to_remove = carton_move.quantity * pack_template.pack_qty

        try:
            # Obtenir la localisation stock
            stock_location = self._get_main_stock_location()
            if not stock_location:
                raise UserError(_("Impossible de trouver l'emplacement de stock principal"))

            current_units = self._get_current_qty(child_product, stock_location)
            new_units = max(0, current_units - units_to_remove)  # Éviter les négatifs

            # Utiliser le wizard standard d'ajustement d'Odoo
            wizard_vals = {
                'product_id': child_product.id,
                'location_id': stock_location.id,
                'new_quantity': new_units,
                'product_tmpl_id': child_product.product_tmpl_id.id,
            }

            wizard = self.env['stock.change.product.qty'].create(wizard_vals)
            wizard.change_product_qty()

            _logger.info(f"[PACK_SALE] {carton_move.quantity} cartons vendus → "
                         f"-{units_to_remove} unités {child_product.display_name}")

        except Exception as e:
            _logger.error(f"[PACK_SALE] Erreur ajustement unités: {str(e)}")
            # Fallback sur méthode directe
            self._direct_inventory_adjustment(child_product, stock_location, -units_to_remove)

    def _get_current_qty(self, product, location):
        """Récupère la quantité actuelle d'un produit dans un emplacement"""
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id)
        ])
        return sum(quants.mapped('quantity'))

    def _get_main_stock_location(self):
        """Récupère l'emplacement de stock principal de la société"""
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if warehouse and warehouse.lot_stock_id:
            return warehouse.lot_stock_id

        # Fallback sur l'emplacement stock par défaut
        try:
            return self.env.ref('stock.stock_location_stock')
        except:
            # Dernier fallback - premier emplacement stock trouvé
            return self.env['stock.location'].search([
                ('usage', '=', 'internal'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)

    def _direct_inventory_adjustment(self, product, location, qty_adjustment):
        """
        Méthode de fallback pour ajustement direct via stock.quant
        Utilise la méthode core _update_available_quantity
        """
        try:
            self.env['stock.quant']._update_available_quantity(
                product,
                location,
                qty_adjustment,
                package_id=False,
                lot_id=False,
                owner_id=False
            )

            # Invalider le cache
            product.invalidate_recordset(['qty_available'])

            _logger.info(f"[DIRECT_ADJUST] Ajustement direct: {qty_adjustment} pour {product.display_name}")

        except Exception as e:
            _logger.error(f"[DIRECT_ADJUST] Échec ajustement direct: {str(e)}")

    def _create_unit_decrement_move(self, unit_product, location, qty_to_remove):
        """
        Crée un mouvement de stock interne pour décrémenter les unités
        """
        # Utiliser l'emplacement d'inventaire pour les ajustements
        inventory_loss_location = self.env.ref('stock.stock_location_inventory', raise_if_not_found=False)
        if not inventory_loss_location:
            # Créer un emplacement virtuel si nécessaire
            inventory_loss_location = self.env['stock.location'].search([
                ('usage', '=', 'inventory'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)

        if not inventory_loss_location:
            raise UserError(_("Impossible de trouver un emplacement d'inventaire"))

        # Créer le mouvement de stock
        move_vals = {
            'name': f'Sync Pack: Décrement unités pour vente carton',
            'product_id': unit_product.id,
            'product_uom_qty': qty_to_remove,
            'product_uom': unit_product.uom_id.id,
            'location_id': location.id,
            'location_dest_id': inventory_loss_location.id,
            'move_type': 'direct',
            'origin': f'Pack sync - {self.name}',
            'company_id': self.company_id.id,
        }

        move = self.env['stock.move'].create(move_vals)
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.write({'qty_done': qty_to_remove})
        move._action_done()

        _logger.info(f"[UNIT_MOVE] Mouvement créé: -{qty_to_remove} {unit_product.name}")

    def _force_unit_adjustment(self, unit_product, qty_adjustment):
        """
        Force un ajustement d'inventaire direct
        """
        try:
            stock_location = self._get_main_stock_location()
            current_qty = self._get_current_qty(unit_product, stock_location)
            new_qty = max(0, current_qty + qty_adjustment)

            # Forcer via stock.quant directement
            quant = self.env['stock.quant'].search([
                ('product_id', '=', unit_product.id),
                ('location_id', '=', stock_location.id)
            ], limit=1)

            if quant:
                quant.quantity = new_qty
            else:
                # Créer un nouveau quant si nécessaire
                self.env['stock.quant'].create({
                    'product_id': unit_product.id,
                    'location_id': stock_location.id,
                    'quantity': new_qty,
                })

            _logger.info(f"[FORCE_ADJUST] Ajustement forcé: {qty_adjustment} pour {unit_product.name}")

        except Exception as e:
            _logger.error(f"[FORCE_ADJUST] Échec ajustement forcé: {str(e)}")