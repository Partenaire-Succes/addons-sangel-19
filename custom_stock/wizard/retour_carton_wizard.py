# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class RetourCartonWizard(models.TransientModel):
    """
    BLOC 3 — Retour carton → sachets.

    Conversion manuelle d'un ou plusieurs cartons déjà en stock vers leurs
    sachets/unités correspondants.

    Principe :
      - Aucun bon de commande, aucun picking, aucun avoir.
      - Ajustement direct du stock (stock.quant) :
          • Carton  : qty -= N cartons convertis
          • Sachet  : qty += N × pack_qty sachets
      - Traçabilité via les mouvements d'inventaire standard d'Odoo.
    """
    _name = 'retour.carton.wizard'
    _description = 'Conversion cartons → sachets (ajustement stock)'
    _rec_name = 'location_id'

    # ─── En-tête ────────────────────────────────────────────────────────────
    location_id = fields.Many2one(
        'stock.location',
        string='Emplacement de stock',
        domain=[('usage', '=', 'internal')],
        required=True,
        default=lambda self: self._default_location(),
        help="Emplacement où se trouvent les cartons et où seront créditées les unités.",
    )
    notes = fields.Char(string='Notes / Référence')

    # ─── Lignes ─────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'retour.carton.wizard.line',
        'wizard_id',
        string='Lignes de conversion',
    )

    # ────────────────────────────────────────────────────────────────────────
    # DEFAULT
    # ────────────────────────────────────────────────────────────────────────
    def _default_location(self):
        wh = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        )
        return wh.lot_stock_id if wh else self.env['stock.location']

    # ────────────────────────────────────────────────────────────────────────
    # ACTION PRINCIPALE
    # ────────────────────────────────────────────────────────────────────────
    def action_valider(self):
        """
        Pour chaque ligne :
          1. Vérifie le stock carton disponible.
          2. Réduit le stock carton via _apply_inventory() → mouvement d'inventaire tracé.
          3. Augmente le stock sachet via _apply_inventory() → mouvement d'inventaire tracé.
        Crée des mouvements de type 'inventory' visibles dans l'historique stock.
        """
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_("Ajoutez au moins une ligne de produit à convertir."))

        messages = []

        for line in self.line_ids:
            tmpl = line.product_id.product_tmpl_id

            # Sécurité : le produit doit être un pack
            if not tmpl.is_pack_parent:
                raise UserError(_(
                    "Le produit '%s' n'est pas configuré comme carton (pack).\n"
                    "Activez 'Article pack (carton)' sur sa fiche."
                ) % line.product_id.display_name)

            child_product = tmpl.pack_child_product_id
            pack_qty = tmpl.pack_qty

            if not child_product or pack_qty <= 0:
                raise UserError(_(
                    "La configuration pack du produit '%s' est incomplète.\n"
                    "Vérifiez le sous-article et la quantité par carton."
                ) % line.product_id.display_name)

            # Stock carton disponible dans cet emplacement
            carton_available = self._get_qty(line.product_id, self.location_id)
            if line.qty > carton_available:
                raise UserError(_(
                    "Stock insuffisant pour le carton '%s'.\n"
                    "Disponible : %.2f  |  Demandé : %.2f"
                ) % (line.product_id.display_name, carton_available, line.qty))

            sachets_to_add = line.qty * pack_qty
            current_sachet_qty = self._get_qty(child_product, self.location_id)

            ref_origine = 'Retour Carton%s' % ((' — ' + self.notes) if self.notes else '')

            # ── Réduction des cartons ── ajustement inventaire avec traçabilité
            carton_quant = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', self.location_id.id),
            ], limit=1)
            if not carton_quant:
                carton_quant = self.env['stock.quant'].create({
                    'product_id': line.product_id.id,
                    'location_id': self.location_id.id,
                    'inventory_quantity': 0,
                })
            carton_quant.inventory_quantity = carton_available - line.qty
            carton_quant = carton_quant.with_context(inventory_origin=ref_origine)
            carton_quant._apply_inventory()

            # ── Ajout des sachets ── ajustement inventaire avec traçabilité
            sachet_quant = self.env['stock.quant'].search([
                ('product_id', '=', child_product.id),
                ('location_id', '=', self.location_id.id),
            ], limit=1)
            if not sachet_quant:
                sachet_quant = self.env['stock.quant'].create({
                    'product_id': child_product.id,
                    'location_id': self.location_id.id,
                    'inventory_quantity': 0,
                })
            sachet_quant.inventory_quantity = current_sachet_qty + sachets_to_add
            sachet_quant = sachet_quant.with_context(inventory_origin=ref_origine)
            sachet_quant._apply_inventory()

            _logger.info(
                "[RETOUR_CARTON] %.2f cartons '%s' → %.2f sachets '%s' @ %s",
                line.qty, line.product_id.display_name,
                sachets_to_add, child_product.display_name,
                self.location_id.display_name,
            )

            messages.append(_(
                "• %(qty)s carton(s) %(carton)s → %(sachets)s sachet(s) %(sachet)s",
                qty=int(line.qty),
                carton=line.product_id.display_name,
                sachets=int(sachets_to_add),
                sachet=child_product.display_name,
            ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conversion effectuée'),
                'message': '\n'.join(messages),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    # ────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ────────────────────────────────────────────────────────────────────────
    def _get_qty(self, product, location):
        """Quantité disponible d'un produit dans un emplacement."""
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ])
        return sum(quants.mapped('quantity'))


class RetourCartonWizardLine(models.TransientModel):
    """Ligne de conversion carton → sachets."""
    _name = 'retour.carton.wizard.line'
    _description = 'Ligne de conversion carton'

    wizard_id = fields.Many2one(
        'retour.carton.wizard',
        required=True,
        ondelete='cascade',
    )

    # ─── Produit carton ──────────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product',
        string='Carton (produit pack)',
        required=True,
        domain=[('product_tmpl_id.is_pack_parent', '=', True)],
    )
    qty = fields.Float(
        string='Nb cartons à convertir',
        required=True,
        default=1.0,
        digits='Product Unit of Measure',
    )

    # ─── Infos calculées (lecture seule) ────────────────────────────────────
    child_product_id = fields.Many2one(
        'product.product',
        string='Sachet / Unité',
        compute='_compute_pack_info',
        store=False,
    )
    pack_qty = fields.Integer(
        string='Unités / carton',
        compute='_compute_pack_info',
        store=False,
    )
    sachets_qty = fields.Float(
        string='Sachets obtenus',
        compute='_compute_sachets_qty',
        store=False,
        digits='Product Unit of Measure',
    )
    stock_carton = fields.Float(
        string='Stock carton disponible',
        compute='_compute_stock_carton',
        store=False,
        digits='Product Unit of Measure',
    )

    @api.depends('product_id')
    def _compute_pack_info(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id if line.product_id else False
            if tmpl and tmpl.is_pack_parent:
                line.child_product_id = tmpl.pack_child_product_id
                line.pack_qty = tmpl.pack_qty
            else:
                line.child_product_id = False
                line.pack_qty = 0

    @api.depends('qty', 'pack_qty')
    def _compute_sachets_qty(self):
        for line in self:
            line.sachets_qty = line.qty * line.pack_qty

    @api.depends('product_id', 'wizard_id.location_id')
    def _compute_stock_carton(self):
        for line in self:
            if line.product_id and line.wizard_id.location_id:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.wizard_id.location_id.id),
                ])
                line.stock_carton = sum(quants.mapped('quantity'))
            else:
                line.stock_carton = 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Réinitialise la quantité à 1 lors du changement de produit."""
        self.qty = 1.0
