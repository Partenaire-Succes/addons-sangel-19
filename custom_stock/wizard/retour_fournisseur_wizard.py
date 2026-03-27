# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class RetourFournisseurWizard(models.TransientModel):
    """
    BLOC 5 — Retour fournisseur.

    Crée un bon de retour (stock.picking outgoing inversé) pour renvoyer
    des articles en stock à un fournisseur, sans nécessiter de picking source.
    Optionnellement génère une demande d'avoir fournisseur (account.move in_refund).

    Différence avec le retour natif Odoo :
      - Le retour natif Odoo part d'un picking existant (réception).
      - Ce wizard fonctionne de façon autonome (stock courant → fournisseur).
    """
    _name = 'retour.fournisseur.wizard'
    _description = 'Retour fournisseur (bon de retour + avoir optionnel)'

    # ─── En-tête ────────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner',
        string='Fournisseur',
        required=True,
    )
    scheduled_date = fields.Datetime(
        string='Date prévue',
        required=True,
        default=fields.Datetime.now,
    )
    location_src_id = fields.Many2one(
        'stock.location',
        string='Emplacement source',
        required=True,
        domain=[('usage', '=', 'internal')],
        default=lambda self: self._default_location(),
        help="Emplacement depuis lequel les articles seront retournés.",
    )
    ref_externe = fields.Char(
        string='Référence externe',
        help="N° de retour fournisseur, BL, numéro de litige…",
    )
    notes = fields.Text(string='Notes')

    # ─── Option comptable ───────────────────────────────────────────────────
    generer_avoir = fields.Boolean(
        string='Générer une demande d\'avoir',
        default=False,
        help="Si coché, crée automatiquement un avoir fournisseur (brouillon) "
             "pour la valeur des articles retournés.",
    )

    # ─── Lignes ─────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'retour.fournisseur.wizard.line',
        'wizard_id',
        string='Articles à retourner',
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
        1. Trouve le type 'Réceptions' (incoming) pour en inverser les emplacements.
        2. Crée le picking retour (stock → fournisseur), state = 'assigned'.
        3. Si generer_avoir = True → crée un avoir fournisseur brouillon.
        4. Redirige vers le picking créé.
        """
        self.ensure_one()

        if not self.line_ids:
            raise UserError(_("Ajoutez au moins une ligne d'article à retourner."))

        # 1. Type de mouvement : incoming inversé = retour vers fournisseur
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('company_id', '=', self.env.company.id),
            ('warehouse_id', '!=', False),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                "Aucun type 'Réceptions' trouvé pour la société %s."
            ) % self.env.company.name)

        # Destination = emplacement fournisseur (inverse de la réception)
        location_dest = picking_type.default_location_src_id
        if not location_dest:
            location_dest = self.env.ref(
                'stock.stock_location_suppliers', raise_if_not_found=False
            )
        if not location_dest:
            raise UserError(_("Emplacement fournisseur introuvable."))

        # 2. Création du picking retour
        picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': self.location_src_id.id,      # stock → fournisseur
            'location_dest_id': location_dest.id,
            'scheduled_date': self.scheduled_date,
            'origin': self.ref_externe or _('Retour fournisseur'),
            'note': self.notes or '',
        })

        # 3. Création des mouvements
        for line in self.line_ids:
            self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.product_uom_id.id,
                'location_id': self.location_src_id.id,
                'location_dest_id': location_dest.id,
                'price_unit': line.price_unit,
                'description_picking': line.product_id.display_name,
            })

        # Confirmation du picking (prêt à être validé manuellement)
        picking.action_confirm()
        picking.action_assign()

        _logger.info(
            "[RETOUR_FOURNISSEUR] Picking %s créé pour %s — %s lignes",
            picking.name, self.partner_id.name, len(self.line_ids),
        )

        # Note chatter : résumé du retour
        lignes_html = ''.join(
            '<li>%s &times; %s (%.2f)</li>' % (
                int(l.qty), l.product_id.display_name, l.price_unit
            )
            for l in self.line_ids
        )
        body = _(
            '<p><b>Bon de retour fournisseur créé</b> — En attente de validation physique</p>'
            '<ul>%(lignes)s</ul>',
            lignes=lignes_html,
        )
        if self.notes:
            body += _('<p><i>%(notes)s</i></p>', notes=self.notes)
        picking.message_post(body=body, message_type='notification')

        # 4. Avoir fournisseur optionnel (brouillon)
        avoir = False
        if self.generer_avoir:
            avoir = self._creer_avoir(picking)

        # 5. Redirection
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bon de retour créé'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ────────────────────────────────────────────────────────────────────────
    # HELPER : création avoir fournisseur
    # ────────────────────────────────────────────────────────────────────────
    def _creer_avoir(self, picking):
        """Crée un avoir fournisseur brouillon lié au retour."""
        invoice_lines = []
        for line in self.line_ids:
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': _(
                    'Retour fournisseur – %(product)s',
                    product=line.product_id.display_name,
                ),
                'quantity': line.qty,
                'price_unit': line.price_unit,
            }))

        avoir = self.env['account.move'].create({
            'move_type': 'in_refund',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'ref': self.ref_externe or _('Retour fournisseur : %s') % picking.name,
            'invoice_line_ids': invoice_lines,
        })

        _logger.info(
            "[RETOUR_FOURNISSEUR] Avoir %s créé (brouillon) pour picking %s",
            avoir.name, picking.name,
        )

        # Lien dans le chatter du picking
        picking.message_post(
            body=_(
                'Avoir fournisseur créé (brouillon) : '
                '<a href="#id=%(id)s&amp;model=account.move">%(name)s</a>',
                id=avoir.id, name=avoir.name or _('Avoir en cours'),
            ),
            message_type='notification',
        )
        return avoir


class RetourFournisseurWizardLine(models.TransientModel):
    """Ligne du retour fournisseur."""
    _name = 'retour.fournisseur.wizard.line'
    _description = 'Ligne de retour fournisseur'

    wizard_id = fields.Many2one(
        'retour.fournisseur.wizard',
        required=True,
        ondelete='cascade',
    )
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
        string='Prix unitaire',
        digits='Product Price',
        help="Prix d'achat de référence pour l'avoir éventuel.",
    )
    stock_disponible = fields.Float(
        string='Stock dispo',
        compute='_compute_stock',
        digits='Product Unit of Measure',
    )

    @api.depends('product_id')
    def _compute_uom(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id if line.product_id else False

    @api.depends('product_id', 'wizard_id.location_src_id')
    def _compute_stock(self):
        for line in self:
            if line.product_id and line.wizard_id.location_src_id:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.wizard_id.location_src_id.id),
                ])
                line.stock_disponible = sum(quants.mapped('quantity'))
            else:
                line.stock_disponible = 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
            self.price_unit = self.product_id.standard_price
            self.qty = 1.0
