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

    facturation_state = fields.Selection([
        ('none', 'Non facturé'),
        ('invoiced', 'Facture créée'),
    ], string="Facturation", default='none', copy=False, readonly=True)
    facture_client_id = fields.Many2one(
        'account.move', string="Facture client", copy=False, readonly=True)

    def action_open_facture_client(self):
        """Smart button : ouvrir la facture client créée depuis ce BL."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Facture client"),
            'res_model': 'account.move',
            'res_id': self.facture_client_id.id,
            'view_mode': 'form',
        }

    def button_validate(self):
        """Override: price validation + sync facture fournisseur + éclatement cartons après réception."""

        # ── 0. Confirmation utilisateur pour les BL liés à une vente ─────────
        # Uniquement pour les livraisons sortantes issues d'un sale.order,
        # et seulement au premier clic (le wizard relance avec le flag).
        if not self.env.context.get('bl_validate_confirmed'):
            bl_ventes = self.filtered(
                lambda p: p.picking_type_id.code == 'outgoing'
                and p.sale_id and p.state not in ('done', 'cancel')
            )
            if bl_ventes:
                wizard = self.env['validate.bl.confirm.wizard'].create({
                    'picking_ids': [(6, 0, self.ids)],
                })
                return {
                    'type': 'ir.actions.act_window',
                    'name': _("Confirmation"),
                    'res_model': 'validate.bl.confirm.wizard',
                    'res_id': wizard.id,
                    'view_mode': 'form',
                    'target': 'new',
                }

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

        # ── 1b. Capturer les prix saisis à la réception AVANT super() ────────
        # super()._action_done() peut recalculer move.price_unit (AVCO, std price…)
        # et écraser le prix saisi par l'utilisateur. On le sauvegarde ici.
        prix_saisis = {}
        for picking in self:
            if picking.picking_type_id.code == 'incoming' and picking.purchase_id:
                for move in picking.move_ids.filtered(
                    lambda m: m.purchase_line_id and m.price_unit
                ):
                    prix_saisis[(picking.id, move.purchase_line_id.id)] = move.price_unit

        # ── 2. Validation standard Odoo ───────────────────────────────────────
        result = super().button_validate()

        # ── 3. Sync facture fournisseur (après réception validée) ─────────────
        for picking in self:
            if (picking.picking_type_id.code == 'incoming'
                    and picking.state == 'done'
                    and picking.purchase_id):
                picking._sync_invoice_from_reception(prix_saisis=prix_saisis)

        # ── 3b. Sync facture client (après livraison validée) ─────────────────
        # Limité strictement aux livraisons issues d'une commande de vente
        # (sale_id) : les autres pickings (POS, inter-société, éclatements…)
        # ne sont pas concernés.
        for picking in self:
            if (picking.picking_type_id.code == 'outgoing'
                    and picking.state == 'done'
                    and picking.sale_id):
                picking._sync_invoice_from_delivery()

        # ── 4. Éclatement automatique cartons → unités ───────────────────────
        for picking in self:
            if picking.picking_type_id.code == 'incoming' and picking.state == 'done':
                picking.action_eclater_cartons_en_unites(auto=True)

        return result

    def _sync_invoice_from_delivery(self):
        """
        Crée et valide automatiquement la facture client depuis la livraison.

        Appelé APRÈS super().button_validate() quand picking = done + lié à
        une commande de vente (sale_id).

        Logique :
          1. Vérifier qu'il y a quelque chose à facturer sur la commande.
          2. Créer la facture via _create_invoices() (équivalent du bouton
             'Créer une facture' sur le devis/commande).
          3. Valider (poster) la facture.
        """
        self.ensure_one()
        order = self.sale_id

        if order.invoice_status != 'to invoice':
            _logger.info(
                "[SYNC_INVOICE_VENTE] Rien à facturer pour la commande %s "
                "(statut facturation : %s) — livraison %s",
                order.name, order.invoice_status, self.name,
            )
            return

        invoices = order._create_invoices()

        for invoice in invoices:
            if invoice.amount_untaxed <= 0:
                _logger.warning(
                    "[SYNC_INVOICE_VENTE] Facture %s non postée : montant = 0 "
                    "— commande %s",
                    invoice.name, order.name,
                )
                continue
            invoice.invoice_date = fields.Date.today()
            invoice.action_post()
            # Marquer le BL comme facturé (badge + smart button dans la vue)
            self.write({
                'facturation_state': 'invoiced',
                'facture_client_id': invoice.id,
            })
            self.message_post(
                body=_("Facture client <b>%s</b> créée et validée automatiquement.") % invoice.name,
                message_type='notification',
            )
            _logger.info(
                "[SYNC_INVOICE_VENTE] Facture %s validée — livraison %s / commande %s",
                invoice.name, self.name, order.name,
            )

    def _sync_invoice_from_reception(self, prix_saisis=None):
        """
        Crée et valide automatiquement la facture fournisseur depuis la réception.

        Appelé APRÈS super().button_validate() quand picking = done + lié à un BC.

        Logique :
          1. Supprimer toute facture brouillon existante liée au BC.
          2. Mettre à jour le prix sur les lignes BC avec le prix de la réception.
             La facture hérite du prix BC → on corrige la source, pas la conséquence.
          3. Créer la facture via action_create_invoice() → quantités et prix corrects.
          4. Valider (poster) la facture.
        """
        self.ensure_one()
        purchase = self.purchase_id

        # ── 1. Nettoyer les factures brouillon existantes ─────────────────────
        draft_invoices = purchase.invoice_ids.filtered(lambda i: i.state == 'draft')
        if draft_invoices:
            draft_invoices.unlink()

        # ── 2. Mettre à jour le prix BC avec le prix saisi à la réception ─────
        # La facture est générée depuis purchase.order.line.price_unit.
        # On corrige la source AVANT de créer la facture pour que le prix
        # de réception remonte naturellement sans patch post-création.
        if prix_saisis:
            for (picking_id, pol_id), price in prix_saisis.items():
                if picking_id == self.id and price:
                    pol = self.env['purchase.order.line'].browse(pol_id)
                    ancien_prix = pol.price_unit
                    pol.write({'price_unit': price})
                    _logger.info(
                        "[SYNC_INVOICE] BC %s ligne %s : prix %s → %s",
                        purchase.name,
                        pol.product_id.display_name,
                        ancien_prix,
                        price,
                    )

        # ── 3. Créer la facture → prix BC mis à jour remontent naturellement ──
        purchase.action_create_invoice()

        invoice = purchase.invoice_ids.filtered(lambda i: i.state == 'draft')
        if not invoice:
            _logger.warning(
                "[SYNC_INVOICE] Aucune facture créée pour le bon de commande %s",
                purchase.name,
            )
            return
        invoice = invoice[0]

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

    def action_eclater_cartons_en_unites(self, auto=False):
        """
        Bouton manuel 'Éclater en unités' — ou appelé automatiquement après validation.

        Création d'un transfert interne : Production → Entrepôt (injecte les unités au bon prix).

        :param auto: True quand appelé depuis button_validate (skip silencieux si non applicable).
        """
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("La réception doit d'abord être validée."))
        if self.picking_type_id.code != 'incoming':
            raise UserError(_("L'éclatement ne s'applique qu'aux réceptions."))

        # ── Protection double-appel ───────────────────────────────────────────
        already_done = self.env['stock.picking'].search([
            ('origin', '=', 'Eclatement cartons — %s' % self.name),
            ('state', '=', 'done'),
        ], limit=1)
        if already_done:
            if auto:
                _logger.info("[ECLATER_AUTO] Déjà effectué pour %s → %s", self.name, already_done.name)
                return
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
            if auto:
                return
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

        label = _('Éclatement cartons automatique') if auto else _('Éclatement cartons effectué')
        self.message_post(
            body=_('%s → transfert unités <b>%s</b> créé.') % (label, explosion_picking.name),
            message_type='notification',
        )
        _logger.info("[ECLATER_AUTO] Éclatement effectué pour %s → %s", self.name, explosion_picking.name)
        if auto:
            return
        return {'type': 'ir.actions.client', 'tag': 'reload'}


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