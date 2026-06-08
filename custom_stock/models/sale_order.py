import logging
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prepare_invoice(self):
        """Override pour s'assurer que les données pack sont préparées avant facturation"""
        res = super()._prepare_invoice()
        # Mettre à jour les équivalences avant facturation si nécessaire
        for line in self.order_line:
            if line.pack_parent_id:
                line._compute_pack_carton_equiv()
        return res

    def _create_invoices(self, grouped=False, final=False, date=None):
        """Override : interdit de facturer une commande tant que ses
        livraisons/réceptions liées ne sont pas validées (état "Fait").
        N'impacte pas les acomptes (méthodes 'percentage'/'fixed'), qui ne
        passent pas par cette surcharge — voir sale.advance.payment.inv._create_invoices.
        """
        for order in self:
            pickings_en_attente = order.picking_ids.filtered(
                lambda p: p.state not in ('done', 'cancel')
            )
            if pickings_en_attente:
                raise UserError(_(
                    "🎭 Alerte facture prématurée !\n\n"
                    "Vous voulez facturer la commande %(order)s alors que sa marchandise\n"
                    "est encore en train de faire du tourisme dans l'entrepôt... 🧳\n\n"
                    "Le client va recevoir une facture... et un courant d'air ? 🌬️\n\n"
                    "👉 Validez d'abord la réception/livraison (%(pickings)s), et tout ira bien !",
                    order=order.name,
                    pickings=", ".join(pickings_en_attente.mapped('name')),
                ))
        return super()._create_invoices(grouped=grouped, final=final, date=date)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    pack_parent_id = fields.Many2one(
        "product.template",
        compute="_compute_pack_parent",
        store=True,
        readonly=True,
        help="Si ce produit est un sous-produit, lien vers l'article carton parent."
    )

    pack_carton_equiv = fields.Float(
        string="Cartons équiv.",
        compute="_compute_pack_carton_equiv",
        store=True,
        readonly=True,
        digits='Product Unit of Measure',
        help="Nombre de cartons équivalents calculés à partir des unités vendues."
    )

    code_article = fields.Char(string='Code article')

    @api.depends("product_id")
    def _compute_pack_parent(self):
        """Trouve le template pack parent pour ce produit unité"""
        for line in self:
            line.pack_parent_id = False
            if not line.product_id:
                continue

            # Chercher si ce produit est un sous-produit d'un pack
            tmpl_pack = self.env["product.template"].search([
                ("is_pack_parent", "=", True),
                ("pack_child_product_id", "=", line.product_id.id),
                ("company_id", "in", [False, line.company_id.id]),
            ], limit=1)

            line.pack_parent_id = tmpl_pack

    @api.depends("product_uom_qty", "pack_parent_id", "pack_parent_id.pack_qty")
    def _compute_pack_carton_equiv(self):
        """Calcule le nombre de cartons équivalents"""
        for line in self:
            cartons = 0.0
            if line.pack_parent_id and line.pack_parent_id.pack_qty > 0:
                cartons = line.product_uom_qty / line.pack_parent_id.pack_qty
            line.pack_carton_equiv = cartons