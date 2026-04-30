from odoo import models, fields, api, _
from odoo.exceptions import UserError
import math
import logging

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    standard_price = fields.Float(string="Prix standard", related='product_id.standard_price', readonly=False)

class StockMoveInherit(models.Model):
    _inherit = 'stock.move'

    amount_total = fields.Float(
        string="Total",
        compute="_compute_amount_total",
        store=True
    )

    @api.depends('quantity', 'price_unit')
    def _compute_amount_total(self):
        for move in self:
            move.amount_total = move.quantity * move.price_unit


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ref_sage = fields.Char(string="Ref SAGE", readonly=True)
    date_sage = fields.Datetime(string="Date SAGE", readonly=True)


    def button_validate(self):
        """Override: price validation uniquement.

        Le sync pack/unité a été retiré de button_validate pour éviter la
        double-décrémentation des SVL (stock.valuation.layer) qui corrompait
        l'AVCO. L'éclatement carton→unité se fait via le bouton dédié
        'Éclater en unités' après validation de la réception.
        """

        # ── 1. Pre-validation checks (before calling super) ──────────────────
        errors = []
        for picking in self:
            if picking.picking_type_id.code == 'incoming':
                for move in picking.move_ids:
                    product_name = move.product_id.display_name
                    if move.price_unit == 0:
                        errors.append(f"{product_name} (Prix = 0)")

        if errors:
            raise UserError(_(
                "🚫 Stop là 😄 !\n\n"
                "On ne réceptionne pas des articles gratuits comme ça 👀.\n"
                "Même les cadeaux ont une valeur sentimentale 😂.\n\n"
                "👉 Donne-moi un prix avant de valider la réception.\n"
                "👉 Sinon, mets la quantité à 0 si tu ne l'as pas reçu.\n\n"
                "📦 Articles concernés :\n- " + "\n- ".join(errors)
            ))

        return super().button_validate()

    def action_eclater_cartons_en_unites(self):
        """
        Bouton manuel 'Éclater en unités' — à appeler après validation d'une réception.

        Crée un transfert interne (carton_location → unit_location) via des
        stock.move propres pour chaque article pack reçu. Le price_unit est
        calculé depuis le mouvement de réception original (prix carton / pack_qty)
        de façon à préserver l'AVCO de l'article unité.
        """
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("La réception doit d'abord être validée."))
        if self.picking_type_id.code != 'incoming':
            raise UserError(_("L'éclatement ne s'applique qu'aux réceptions."))

        pack_moves = []
        for move in self.move_ids.filtered(lambda m: m.state == 'done' and m.quantity > 0):
            pack_template = self._get_pack_template_for_move(move)
            if not pack_template:
                continue
            pack_moves.append((move, pack_template))

        if not pack_moves:
            raise UserError(_("Aucun article pack (carton) trouvé dans cette réception."))

        # Emplacement virtuel "Explosions pack" (production) comme source intermédiaire
        production_loc = self.env.ref('stock.location_production', raise_if_not_found=False)
        if not production_loc:
            raise UserError(_("Emplacement de production introuvable."))

        internal_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('company_id', '=', self.company_id.id),
            ('warehouse_id', '!=', False),
        ], limit=1)
        if not internal_type:
            raise UserError(_("Aucun type 'Transfert interne' trouvé."))

        dest_location = self.location_dest_id
        picking_vals = {
            'picking_type_id': internal_type.id,
            'location_id': production_loc.id,     # source virtuelle (Production)
            'location_dest_id': dest_location.id,  # destination = entrepôt réception
            'origin': 'Eclatement cartons — %s' % self.name,
            'company_id': self.company_id.id,
        }
        explosion_picking = self.env['stock.picking'].create(picking_vals)

        for move, pack_template in pack_moves:
            child_product = pack_template.pack_child_product_id
            units_qty = move.quantity * pack_template.pack_qty
            unit_price = (
                move.price_unit / pack_template.pack_qty
                if pack_template.pack_qty else child_product.standard_price
            )
            self.env['stock.move'].create({
                'picking_id': explosion_picking.id,
                'product_id': child_product.id,
                'product_uom_qty': units_qty,
                'product_uom': child_product.uom_id.id,
                'location_id': production_loc.id,
                'location_dest_id': dest_location.id,
                'price_unit': unit_price,
                'name': 'Eclatement %s -> %s' % (pack_template.name, child_product.display_name),
                'origin': self.name,
                'company_id': self.company_id.id,
            })

        explosion_picking.action_confirm()

        # Pour les sources virtuelles (Production), action_assign ne cree pas
        # de move lines. On les cree explicitement puis on valide.
        for sm in explosion_picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            if not sm.move_line_ids:
                self.env['stock.move.line'].create({
                    'move_id': sm.id,
                    'picking_id': explosion_picking.id,
                    'product_id': sm.product_id.id,
                    'product_uom_id': sm.product_uom.id,
                    'quantity': sm.product_uom_qty,
                    'location_id': sm.location_id.id,
                    'location_dest_id': sm.location_dest_id.id,
                })
            else:
                for ml in sm.move_line_ids:
                    ml.quantity = sm.product_uom_qty

        explosion_picking.with_context(skip_backorder=True, skip_immediate=True).button_validate()

        self.message_post(
            body=_('Éclatement cartons effectué → transfert <b>%s</b> créé.') % explosion_picking.name,
            message_type='notification',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Éclatement cartons'),
            'res_model': 'stock.picking',
            'res_id': explosion_picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # _process_pack_explosion et _process_unit_to_pack_sync supprimés :
    # ils créaient des ajustements d'inventaire sur du stock déjà modifié
    # par le picking → double-décrémentation → corruption AVCO.

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

    # Méthodes supprimées (corrompaient l'AVCO par double-décrémentation SVL) :
    # _create_inventory_adjustment_for_units, _process_template_unit_sync,
    # _update_template_counter_and_process, _create_inventory_adjustment_for_cartons,
    # _decrement_units_for_sold_cartons
    # → remplacées par action_eclater_cartons_en_unites (transfert interne propre).

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

    # _direct_inventory_adjustment, _create_unit_decrement_move et _force_unit_adjustment
    # supprimés : écrire directement sur stock.quant.quantity bypasse le SVL et
    # corrompt l'AVCO de façon irréversible. Aucun fallback silencieux accepté.