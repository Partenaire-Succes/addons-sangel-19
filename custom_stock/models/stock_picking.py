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
        """Override: price validation + sync facture fournisseur après réception.

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

        # ── 2. Validation standard Odoo ───────────────────────────────────────
        result = super().button_validate()

        # ── 3. Sync facture fournisseur (après réception validée) ─────────────
        for picking in self:
            if (picking.picking_type_id.code == 'incoming'
                    and picking.state == 'done'
                    and picking.purchase_id):
                picking._sync_invoice_from_reception()

        return result

    def _sync_invoice_from_reception(self):
        """
        Crée et valide automatiquement la facture fournisseur depuis la réception.

        Appelé APRÈS super().button_validate() quand picking = done + lié à un BC.

        Logique :
          1. Supprimer toute facture brouillon existante liée au BC
             (créée prématurément à la confirmation avec qty=0).
          2. Laisser Odoo créer la facture via action_create_invoice()
             — à ce stade qty_received > 0, donc les lignes sont correctes.
          3. Si le prix de réception diffère du BC, l'appliquer sur les lignes.
          4. Valider (poster) la facture.
        """
        self.ensure_one()
        purchase = self.purchase_id

        # ── 1. Nettoyer les factures brouillon existantes (qty=0) ─────────────
        draft_invoices = purchase.invoice_ids.filtered(lambda i: i.state == 'draft')
        if draft_invoices:
            draft_invoices.unlink()

        # ── 2. Créer la facture avec les quantités réellement reçues ──────────
        # qty_received est maintenant > 0 → Odoo génère des lignes correctes.
        purchase.action_create_invoice()

        invoice = purchase.invoice_ids.filtered(lambda i: i.state == 'draft')
        if not invoice:
            _logger.warning(
                "[SYNC_INVOICE] Aucune facture créée pour le bon de commande %s",
                purchase.name,
            )
            return
        invoice = invoice[0]

        # ── 3. Corriger le prix unitaire si différent entre réception et BC ───
        price_by_pol = {}
        for move in self.move_ids.filtered(
            lambda m: m.state == 'done' and m.purchase_line_id and m.price_unit
        ):
            pol_id = move.purchase_line_id.id
            if move.price_unit != move.purchase_line_id.price_unit:
                price_by_pol[pol_id] = move.price_unit

        if price_by_pol:
            for inv_line in invoice.invoice_line_ids.filtered(
                lambda l: not l.display_type and l.purchase_line_id
            ):
                pol_id = inv_line.purchase_line_id.id
                if pol_id in price_by_pol:
                    inv_line.write({'price_unit': price_by_pol[pol_id]})

        # ── 4. Valider la facture ─────────────────────────────────────────────
        if invoice.amount_untaxed <= 0:
            _logger.warning(
                "[SYNC_INVOICE] Facture %s non postée : montant total = 0",
                invoice.name,
            )
            return

        invoice.invoice_date = fields.Date.today()
        invoice.action_post()
        _logger.info(
            "[SYNC_INVOICE] Facture %s validée — réception %s / commande %s",
            invoice.name, self.name, purchase.name,
        )

    def action_eclater_cartons_en_unites(self):
        """
        Bouton manuel 'Éclater en unités' — à appeler après validation d'une réception.

        Deux transferts internes sont créés :
          1. Consommation cartons : Entrepôt → Production (retire le stock carton, AVCO correct)
          2. Création unités    : Production → Entrepôt  (injecte les unités au bon prix)

        La vue produit affiche pack_equiv_cartons_available = unités / pack_qty en temps réel.
        """
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("La réception doit d'abord être validée."))
        if self.picking_type_id.code != 'incoming':
            raise UserError(_("L'éclatement ne s'applique qu'aux réceptions."))

        # ── Protection double-clic ────────────────────────────────────────────
        already_done = self.env['stock.picking'].search([
            ('origin', '=', 'Eclatement cartons — %s' % self.name),
            ('state', '=', 'done'),
        ], limit=1)
        if already_done:
            raise UserError(_(
                "L'éclatement a déjà été effectué pour cette réception.\n"
                "Transfert existant : %s"
            ) % already_done.name)

        pack_moves = []
        for move in self.move_ids.filtered(lambda m: m.state == 'done' and m.quantity > 0):
            pack_template = self._get_pack_template_for_move(move)
            if not pack_template:
                continue
            pack_moves.append((move, pack_template))

        if not pack_moves:
            raise UserError(_("Aucun article pack (carton) trouvé dans cette réception."))

        # En Odoo 19, l'emplacement Production est par société (pas d'XML ID global).
        # Récupération via ir.default (méthode officielle Odoo 19), avec fallback recherche.
        production_loc_id = self.env['ir.default']._get(
            'product.template', 'property_stock_production',
            company_id=self.company_id.id,
        )
        production_loc = self.env['stock.location'].browse(production_loc_id) if production_loc_id else False
        if not production_loc:
            production_loc = self.env['stock.location'].search([
                ('usage', '=', 'production'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        if not production_loc:
            raise UserError(_("Emplacement de production introuvable. Vérifiez la configuration des emplacements virtuels (Inventaire → Configuration → Entrepôts)."))

        internal_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('company_id', '=', self.company_id.id),
            ('warehouse_id', '!=', False),
        ], limit=1)
        if not internal_type:
            raise UserError(_("Aucun type 'Transfert interne' trouvé."))

        dest_location = self.location_dest_id

        # Crée les unités depuis Production → Entrepôt.
        # Le stock carton physique n'est pas touché — il reste visible dans l'inventaire.
        # L'affichage se fait via pack_equiv_cartons_available qui combine
        # cartons physiques non éclatés + unités enfant / pack_qty.
        explosion_picking = self.env['stock.picking'].create({
            'picking_type_id': internal_type.id,
            'location_id': production_loc.id,     # source virtuelle (Production)
            'location_dest_id': dest_location.id,  # destination = entrepôt réception
            'origin': 'Eclatement cartons — %s' % self.name,
            'company_id': self.company_id.id,
        })

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
            body=_('Éclatement cartons effectué → transfert unités <b>%s</b> créé.') % explosion_picking.name,
            message_type='notification',
        )
        # Retourner un reload de la réception (pas le formulaire du picking éclatement).
        # Ouvrir ce formulaire plante sur _compute_forecast_information (bug Odoo 19 :
        # KeyError sur (warehouse_id, date) pour les mouvements depuis emplacement virtuel).
        return {'type': 'ir.actions.client', 'tag': 'reload'}

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