# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class RetourInventaireWizard(models.TransientModel):
    """
    BLOC 4 — Retour inventaire : génération d'avoir/facture fournisseur
    depuis un inventaire physique terminé.

    Flux :
      physical.inventory (state='done')
        → bouton "Générer un avoir"
        → ce wizard (pré-rempli avec les lignes à qty_diff < 0)
        → account.move de type 'in_refund' ou 'in_invoice'
    """
    _name = 'retour.inventaire.wizard'
    _description = 'Génération avoir/facture depuis inventaire physique'

    # ─── En-tête ────────────────────────────────────────────────────────────
    inventory_id = fields.Many2one(
        'physical.inventory',
        string='Inventaire source',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Fournisseur',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        help="Fournisseur à qui adresser l'avoir ou la facture.",
    )
    invoice_date = fields.Date(
        string='Date du document',
        required=True,
        default=fields.Date.today,
    )
    type_document = fields.Selection([
        ('in_refund', 'Avoir fournisseur (crédit reçu)'),
        ('in_invoice', 'Facture fournisseur (montant dû)'),
    ], string='Type de document', default='in_refund', required=True,
       help="• Avoir fournisseur : le fournisseur vous crédite (manquants à sa charge).\n"
            "• Facture fournisseur : vous devez payer (rare — ajustement positif).",
    )
    ref_externe = fields.Char(
        string='Référence externe',
        help="N° de BL, contrat, ou toute référence utile.",
    )

    # ─── Lignes ─────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'retour.inventaire.wizard.line',
        'wizard_id',
        string='Lignes à inclure',
    )

    # ────────────────────────────────────────────────────────────────────────
    # PRÉ-REMPLISSAGE AUTO à l'ouverture
    # ────────────────────────────────────────────────────────────────────────
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        inventory_id = self.env.context.get('default_inventory_id')
        if not inventory_id or 'line_ids' not in fields_list:
            return res

        inventory = self.env['physical.inventory'].browse(inventory_id)
        lines_vals = []
        for inv_line in inventory.physical_line_ids.filtered(lambda l: l.qty_diff < 0 and l.active):
            lines_vals.append((0, 0, {
                'inventory_line_id': inv_line.id,
                'product_id': inv_line.product_id.id,
                'qty_manquant': abs(inv_line.qty_diff),
                'qty_retour': abs(inv_line.qty_diff),
                'price_unit': inv_line.standard_price,
                'selected': True,
            }))
        res['line_ids'] = lines_vals
        return res

    # ────────────────────────────────────────────────────────────────────────
    # ACTIONS
    # ────────────────────────────────────────────────────────────────────────
    def action_generer_document(self):
        """
        Génère l'account.move (avoir ou facture fournisseur)
        à partir des lignes sélectionnées, puis ouvre le document.
        """
        self.ensure_one()

        lines_selected = self.line_ids.filtered(
            lambda l: l.selected and l.qty_retour > 0
        )
        if not lines_selected:
            raise UserError(_(
                "Aucune ligne sélectionnée avec une quantité > 0.\n"
                "Cochez au moins une ligne et vérifiez les quantités."
            ))

        # Construction des lignes de facture
        invoice_lines = []
        for line in lines_selected:
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': _(
                    'Manquant inventaire %(inv)s – %(product)s',
                    inv=self.inventory_id.name,
                    product=line.product_id.display_name,
                ),
                'quantity': line.qty_retour,
                'price_unit': line.price_unit,
            }))

        # Création du document comptable
        ref = self.ref_externe or _(
            'Retour inventaire : %s'
        ) % self.inventory_id.name

        move = self.env['account.move'].create({
            'move_type': self.type_document,
            'partner_id': self.partner_id.id,
            'invoice_date': self.invoice_date,
            'ref': ref,
            'invoice_line_ids': invoice_lines,
        })

        _logger.info(
            "[RETOUR_INVENTAIRE] %s créé (id=%s) pour inventaire '%s' — %s lignes",
            self.type_document, move.id, self.inventory_id.name, len(lines_selected),
        )

        # Lien chatter sur l'inventaire
        self.inventory_id.message_post(
            body=_(
                'Document comptable généré : <a href="#id=%(id)s&model=account.move">%(ref)s</a>',
                id=move.id, ref=ref,
            ),
            subject=_('Retour inventaire — document créé'),
            message_type='notification',
        )

        # Ouverture du document créé
        return {
            'type': 'ir.actions.act_window',
            'name': _('Document généré'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }


class RetourInventaireWizardLine(models.TransientModel):
    """Ligne du wizard de retour inventaire."""
    _name = 'retour.inventaire.wizard.line'
    _description = 'Ligne wizard retour inventaire'

    wizard_id = fields.Many2one(
        'retour.inventaire.wizard',
        required=True,
        ondelete='cascade',
    )
    inventory_line_id = fields.Many2one(
        'physical.inventory.line',
        string='Ligne inventaire',
        readonly=True,
    )

    # ─── Produit ────────────────────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product',
        string='Article',
        required=True,
        readonly=True,
    )

    # ─── Quantités ──────────────────────────────────────────────────────────
    qty_manquant = fields.Float(
        string='Manquant inventaire',
        readonly=True,
        digits='Product Unit of Measure',
        help="Écart constaté lors de l'inventaire (valeur absolue de qty_diff).",
    )
    qty_retour = fields.Float(
        string='Qté à inclure',
        required=True,
        digits='Product Unit of Measure',
        help="Quantité à inscrire dans le document comptable (modifiable).",
    )
    price_unit = fields.Float(
        string='Prix unitaire',
        required=True,
        digits='Product Price',
    )
    subtotal = fields.Float(
        string='Sous-total',
        compute='_compute_subtotal',
        digits='Product Price',
    )

    # ─── Sélection ──────────────────────────────────────────────────────────
    selected = fields.Boolean(
        string='Inclure',
        default=True,
    )

    @api.depends('qty_retour', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty_retour * line.price_unit
