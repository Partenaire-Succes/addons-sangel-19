# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class ReceptionDirecteWizard(models.TransientModel):
    """Réception directe sans bon de commande fournisseur."""
    _name = 'reception.directe.wizard'
    _description = 'Réception directe sans commande fournisseur'

    partner_id = fields.Many2one(
        'res.partner',
        string='Fournisseur',
    )
    scheduled_date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        required=True,
    )
    location_dest_id = fields.Many2one(
        'stock.location',
        string='Emplacement de destination',
        domain=[('usage', '=', 'internal')],
        required=True,
        default=lambda self: self._default_location_dest(),
    )
    notes = fields.Char(string='Référence / Notes')

    line_ids = fields.One2many(
        'reception.directe.wizard.line',
        'wizard_id',
        string='Produits',
    )

    def _default_location_dest(self):
        wh = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1
        )
        return wh.lot_stock_id if wh else self.env['stock.location']

    def action_valider(self):
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_("Ajoutez au moins un produit à réceptionner."))

        # Type de réception incoming
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('company_id', '=', self.env.company.id),
            ('warehouse_id', '!=', False),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                "Aucun type 'Réceptions' trouvé pour la société %s."
            ) % self.env.company.name)

        location_src = picking_type.default_location_src_id or self.env.ref(
            'stock.stock_location_suppliers', raise_if_not_found=False
        )
        if not location_src:
            raise UserError(_("Emplacement source fournisseur introuvable."))

        # Création du picking
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id if self.partner_id else False,
            'picking_type_id': picking_type.id,
            'location_id': location_src.id,
            'location_dest_id': self.location_dest_id.id,
            'scheduled_date': self.scheduled_date,
            'origin': 'Réception Directe',
            'note': self.notes or '',
        })

        # Création des mouvements
        line_move_map = {}
        for line in self.line_ids:
            # Si nouveau_prix renseigné, c'est ce coût qui est gravé sur le mouvement
            prix_mouvement = (
                line.nouveau_prix
                if line.nouveau_prix and line.nouveau_prix > 0
                else line.price_unit
            )
            move = self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.product_uom_id.id,
                'location_id': location_src.id,
                'location_dest_id': self.location_dest_id.id,
                'price_unit': prix_mouvement,
                'description_picking': line.product_id.display_name,
            })
            line_move_map[line.id] = move

        picking.action_confirm()
        picking.action_assign()

        # Forcer qty reçue sur chaque move.line
        for line in self.line_ids:
            move = line_move_map[line.id]
            if move.move_line_ids:
                for ml in move.move_line_ids:
                    ml.quantity = line.qty
            else:
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'quantity': line.qty,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                })

        # Validation (déclenche explosion pack si applicable)
        picking.with_context(skip_backorder=True).button_validate()

        # Mise à jour du nouveau prix d'achat + traçabilité chatter
        prix_changes = []
        for line in self.line_ids:
            if line.nouveau_prix and line.nouveau_prix > 0:
                ancien_prix = line.price_unit
                line.product_id.product_tmpl_id.purchase_new_price = line.nouveau_prix
                prix_changes.append(
                    '&bull; <b>%s</b> : %.2f &rarr; <b>%.2f</b>'
                    % (line.product_id.display_name, ancien_prix, line.nouveau_prix)
                )

        # Note chatter : toujours poster le résumé de la réception
        lignes_html = ''.join(
            '<li>%s &times; %s</li>' % (int(l.qty), l.product_id.display_name)
            for l in self.line_ids
        )
        body = _(
            '<p><b>Réception directe validée</b></p>'
            '<ul>%(lignes)s</ul>',
            lignes=lignes_html,
        )
        if self.notes:
            body += _('<p><i>Référence : %(ref)s</i></p>', ref=self.notes)
        if prix_changes:
            body += _(
                '<p><b>Mises à jour prix d\'achat :</b><br/>%(changes)s</p>',
                changes='<br/>'.join(prix_changes),
            )
        picking.message_post(body=body, message_type='notification')

        _logger.info("[RECEPTION_DIRECTE] Picking %s créé — %s lignes", picking.name, len(self.line_ids))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Réception validée'),
                'message': _('Bon de réception %s créé avec succès.') % picking.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class ReceptionDirecteWizardLine(models.TransientModel):
    _name = 'reception.directe.wizard.line'
    _description = 'Ligne de réception directe'

    wizard_id = fields.Many2one('reception.directe.wizard', required=True, ondelete='cascade')

    product_id = fields.Many2one(
        'product.product',
        string='Article',
        required=True,
        domain=[('type', 'in', ['product', 'consu'])],
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unité',
        compute='_compute_uom',
        store=True,
        readonly=False,
    )
    qty = fields.Float(
        string='Quantité',
        required=True,
        default=1.0,
        digits='Product Unit of Measure',
    )
    price_unit = fields.Float(
        string='Coût actuel',
        digits='Product Price',
        readonly=True,
        help="Coût effectif actuel du produit (nouveau prix si défini, sinon prix standard).",
    )
    nouveau_prix = fields.Float(
        string='Nouveau prix d\'achat',
        digits='Product Price',
        help="Laisser à 0 pour conserver le coût actuel. "
             "Si renseigné, devient le nouveau coût de référence du produit.",
    )

    @api.depends('product_id')
    def _compute_uom(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id if line.product_id else False

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            self.price_unit = (
                self.product_id.product_tmpl_id.effective_cost
                or self.product_id.standard_price
            )
            self.nouveau_prix = 0.0
