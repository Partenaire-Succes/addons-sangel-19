# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class ReceptionCorrectionStockWizard(models.TransientModel):
    """
    Wizard de correction des quantités d'une réception directe validée.

    Approche différentielle :
      - delta > 0 (trop peu reçu) → picking entrant complémentaire validé
      - delta < 0 (trop reçu)    → picking retour (stock → fournisseur) validé

    Toutes les corrections sont liées à la réception d'origine dans le chatter.
    La comptabilité reste cohérente car on crée de vrais mouvements de stock.
    """
    _name = 'reception.correction.stock.wizard'
    _description = 'Corriger les quantités de stock d\'une réception validée'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Réception d\'origine',
        required=True,
        readonly=True,
    )
    motif = fields.Char(
        string='Motif de la correction',
        required=True,
        help="Obligatoire pour la traçabilité. Ex: 'Erreur de saisie quantité', 'Produit manquant BL'…",
    )
    line_ids = fields.One2many(
        'reception.correction.stock.wizard.line',
        'wizard_id',
        string='Lignes à corriger',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = (
            self.env.context.get('active_id')
            or self.env.context.get('default_picking_id')
        )
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            if picking.exists():
                lines = []
                for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                    lines.append((0, 0, {
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'qty_originale': move.quantity,
                        'qty_correcte': move.quantity,
                        'price_unit': move.price_unit,
                    }))
                res['picking_id'] = picking.id
                res['line_ids'] = lines
        return res

    def action_appliquer(self):
        self.ensure_one()
        picking = self.picking_id

        if picking.state != 'done':
            raise UserError(_(
                "Ce bon de réception n'est pas encore validé."
            ))
        if not self.motif or not self.motif.strip():
            raise UserError(_("Le motif de correction est obligatoire."))

        # ── Calcul des deltas ─────────────────────────────────────────────────
        retour_lines = []   # (line, qty_abs) — trop reçu → retour
        extra_lines  = []   # (line, qty)     — trop peu reçu → complément

        for line in self.line_ids:
            delta = line.qty_correcte - line.qty_originale
            if abs(delta) < 0.001:
                continue
            if delta < 0:
                retour_lines.append((line, abs(delta)))
            else:
                extra_lines.append((line, delta))

        if not retour_lines and not extra_lines:
            raise UserError(_(
                "Aucune modification détectée. "
                "Les quantités saisies sont identiques aux quantités d'origine."
            ))

        # ── Récupération du type de picking ───────────────────────────────────
        picking_type = picking.picking_type_id
        if not picking_type:
            raise UserError(_("Type de picking introuvable sur la réception d'origine."))

        created_pickings = []

        # ── Picking de retour (trop reçu → stock → fournisseur) ───────────────
        if retour_lines:
            retour = self.env['stock.picking'].create({
                'partner_id': picking.partner_id.id if picking.partner_id else False,
                'picking_type_id': picking_type.id,
                'location_id': picking.location_dest_id.id,   # depuis le stock
                'location_dest_id': picking.location_id.id,   # vers fournisseur
                'scheduled_date': fields.Datetime.now(),
                'origin': 'CORR-/%s' % picking.name,
                'note': 'Correction: %s' % self.motif,
                'ref_sage': picking.ref_sage or '',
            })
            qty_by_product = {}
            for line, qty in retour_lines:
                self.env['stock.move'].create({
                    'picking_id': retour.id,
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': picking.location_dest_id.id,
                    'location_dest_id': picking.location_id.id,
                    'price_unit': line.price_unit,
                    'description_picking': line.product_id.display_name,
                })
                pid = line.product_id.id
                qty_by_product[pid] = qty_by_product.get(pid, 0.0) + qty

            retour.action_confirm()
            retour.action_assign()
            self._force_quantities(retour, qty_by_product)
            retour.with_context(
                skip_backorder=True,
                skip_immediate=True,
            ).button_validate()
            created_pickings.append(('retour', retour))
            _logger.info(
                "[CORRECTION_STOCK] Retour %s créé pour correction de %s",
                retour.name, picking.name,
            )

        # ── Picking complémentaire (trop peu reçu → fournisseur → stock) ──────
        if extra_lines:
            extra = self.env['stock.picking'].create({
                'partner_id': picking.partner_id.id if picking.partner_id else False,
                'picking_type_id': picking_type.id,
                'location_id': picking.location_id.id,       # depuis fournisseur
                'location_dest_id': picking.location_dest_id.id,  # vers stock
                'scheduled_date': fields.Datetime.now(),
                'origin': 'CORR+/%s' % picking.name,
                'note': 'Correction: %s' % self.motif,
                'ref_sage': picking.ref_sage or '',
            })
            qty_by_product = {}
            for line, qty in extra_lines:
                self.env['stock.move'].create({
                    'picking_id': extra.id,
                    'product_id': line.product_id.id,
                    'product_uom_qty': qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'price_unit': line.price_unit,
                    'description_picking': line.product_id.display_name,
                })
                pid = line.product_id.id
                qty_by_product[pid] = qty_by_product.get(pid, 0.0) + qty

            extra.action_confirm()
            extra.action_assign()
            self._force_quantities(extra, qty_by_product)
            extra.with_context(
                skip_backorder=True,
                skip_immediate=True,
            ).button_validate()
            created_pickings.append(('extra', extra))
            _logger.info(
                "[CORRECTION_STOCK] Complément %s créé pour correction de %s",
                extra.name, picking.name,
            )

        # ── Traçabilité chatter sur la réception d'origine ───────────────────
        lignes_html = ''
        for line in self.line_ids:
            delta = line.qty_correcte - line.qty_originale
            if abs(delta) < 0.001:
                continue
            signe = '+' if delta > 0 else ''
            lignes_html += (
                '<li><b>%s</b> : %g → %g (<b>%s%g</b>)</li>'
                % (line.product_id.display_name,
                   line.qty_originale, line.qty_correcte, signe, delta)
            )

        pickings_links = ', '.join(
            '<b>%s</b> (%s)' % (p.name, 'retour' if t == 'retour' else 'complément')
            for t, p in created_pickings
        )
        body = _(
            '<p><b>Correction de stock appliquée</b></p>'
            '<p><i>Motif : %(motif)s</i></p>'
            '<ul>%(lignes)s</ul>'
            '<p>Picking(s) de correction créé(s) : %(links)s</p>',
            motif=self.motif,
            lignes=lignes_html,
            links=pickings_links,
        )
        picking.message_post(body=body, message_type='notification')

        # Lier la correction dans le chatter des pickings créés
        for _t, corr_picking in created_pickings:
            corr_picking.message_post(
                body=_(
                    '<p>Picking de correction lié à la réception d\'origine : <b>%s</b></p>'
                    '<p><i>Motif : %s</i></p>'
                ) % (picking.name, self.motif),
                message_type='notification',
            )

        msg = _('%(n)s picking(s) de correction créé(s) et validé(s).') % {
            'n': len(created_pickings)
        }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correction de stock appliquée'),
                'message': msg,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _force_quantities(self, picking, qty_by_product):
        """Force les quantités réelles sur les move lines (même logique que la réception directe)."""
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            total_qty = qty_by_product.get(move.product_id.id, move.product_uom_qty)
            if move.move_line_ids:
                for ml in move.move_line_ids:
                    ml.quantity = total_qty
            else:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': total_qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                })


class ReceptionCorrectionStockWizardLine(models.TransientModel):
    _name = 'reception.correction.stock.wizard.line'
    _description = 'Ligne de correction de stock'

    wizard_id = fields.Many2one(
        'reception.correction.stock.wizard',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Article',
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unité',
    )
    price_unit = fields.Float(
        string='Prix unitaire',
        digits='Product Price',
    )
    qty_originale = fields.Float(
        string='Qté reçue (originale)',
        digits='Product Unit of Measure',
    )
    qty_correcte = fields.Float(
        string='Qté correcte',
        digits='Product Unit of Measure',
        required=True,
    )
    delta = fields.Float(
        string='Écart',
        digits='Product Unit of Measure',
        compute='_compute_delta',
        store=False,
    )

    @api.depends('qty_correcte', 'qty_originale')
    def _compute_delta(self):
        for line in self:
            line.delta = line.qty_correcte - line.qty_originale
