from odoo import models, fields, api, _
from odoo.exceptions import UserError
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
        """Override: price validation + sync facture fournisseur après réception."""

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

        return result

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

