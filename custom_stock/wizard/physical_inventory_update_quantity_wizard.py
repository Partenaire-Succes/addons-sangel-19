# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PhysicalInventoryUpdateQuantityWizard(models.TransientModel):
    """
    Corrige le champ `quantity` (stock système) sur des physical.inventory.line
    déjà créées, en le recalculant par rejeu des stock.move.line validés
    jusqu'à la date choisie (entrées - sorties sur l'emplacement de la ligne),
    plutôt que de relire le seul `stock.quant` (qui ne reflète que l'instant
    présent) ou `qty_available` (sensible aux mouvements postérieurs à la date
    si on compare au stock du jour même).

    Utile notamment pour corriger les lignes où le système a enregistré
    `quantity = 0` à tort (produit sans quant au moment de la génération de
    l'inventaire), y compris sur des inventaires déjà à l'état 'done' — la
    correction ne rejoue pas le mouvement de stock déjà validé, elle ne fait
    que corriger la donnée de référence et l'écart/valorisation recalculés.
    """
    _name = 'physical.inventory.update.quantity.wizard'
    _description = "Assistant de correction des quantités d'inventaire"

    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Emplacement',
        domain=[('usage', '=', 'internal')],
        help="Laisser vide pour cibler tous les emplacements internes de la société.",
    )
    date = fields.Date(
        string='Date du stock à prendre',
        required=True,
        default=fields.Date.context_today,
        help="Quantité système reconstituée à cette date (rejoue les mouvements de stock "
             "faits après cette date) — pas seulement la quantité actuelle.",
    )
    date_from = fields.Date(
        string="Période — du",
        help="Sélectionne les lignes dont l'inventaire physique a une date dans cette période. "
             "Laisser vide pour ne pas borner la période.",
    )
    date_to = fields.Date(
        string="Période — au",
        default=fields.Date.context_today,
    )
    line_ids = fields.One2many(
        'physical.inventory.update.quantity.wizard.line',
        'wizard_id',
        string='Lignes',
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise UserError(_("La date de début de la période doit être antérieure à la date de fin."))

    def _get_quantity_at_date(self, location, product_ids, to_datetime):
        """Quantité nette par produit sur `location`, calculée par rejeu des
        stock.move.line validés jusqu'à `to_datetime` (entrées - sorties)."""
        if not product_ids:
            return {}
        self.env.cr.execute("""
            SELECT product_id,
                   SUM(CASE WHEN location_dest_id = %s THEN quantity ELSE -quantity END) AS qty
            FROM stock_move_line
            WHERE product_id = ANY(%s)
              AND state = 'done'
              AND date <= %s
              AND (location_id = %s OR location_dest_id = %s)
            GROUP BY product_id
        """, [location.id, list(product_ids), to_datetime, location.id, location.id])
        return dict(self.env.cr.fetchall())

    def action_search_lines(self):
        """Recherche les lignes correspondant aux filtres et affiche un aperçu
        (ancienne/nouvelle quantité) avant toute écriture."""
        self.ensure_one()

        domain = [
            ('active', '=', True),
            ('inventory_physical_id.company_id', '=', self.company_id.id),
            ('quantity', '=', 0),
            ('valorisation', '!=', 0),
        ]
        if self.date_from:
            domain.append(('inventory_physical_id.date_done', '>=', datetime.combine(self.date_from, time.min)))
        if self.date_to:
            domain.append(('inventory_physical_id.date_done', '<=', datetime.combine(self.date_to, time.max)))
        if self.location_id:
            domain.append(('location_id', '=', self.location_id.id))

        inventory_lines = self.env['physical.inventory.line'].search(domain)

        to_datetime = datetime.combine(self.date, time.max)
        lines_by_location = defaultdict(list)
        for inv_line in inventory_lines:
            lines_by_location[inv_line.location_id].append(inv_line)

        self.line_ids.unlink()
        lines_vals = []
        for location, lines in lines_by_location.items():
            location_lines = sum(lines, self.env['physical.inventory.line'])
            qty_by_product = self._get_quantity_at_date(
                location, location_lines.mapped('product_id').ids, to_datetime,
            )
            for inv_line in lines:
                # Ne cible que les lignes où le stock système est réellement faux :
                # quantity=0 alors que le stock reconstitué à la date choisie est différent de 0.
                new_qty = qty_by_product.get(inv_line.product_id.id, 0.0)
                # if not new_qty:
                #     continue
                lines_vals.append((0, 0, {
                    'inventory_line_id': inv_line.id,
                    'inventory_physical_id': inv_line.inventory_physical_id.id,
                    'product_id': inv_line.product_id.id,
                    'location_id': inv_line.location_id.id,
                    'old_quantity': inv_line.quantity,
                    'new_quantity': new_qty,
                    'selected': bool(new_qty),
                }))
        if not lines_vals:
            raise UserError(_(
                "Aucune ligne trouvée : il faut quantity=0 sur la ligne ET un stock "
                "reconstitué à la date choisie différent de 0 pour ces filtres."
            ))
        self.line_ids = lines_vals

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        """Écrit la nouvelle quantité sur les physical.inventory.line sélectionnées."""
        self.ensure_one()

        lines_selected = self.line_ids.filtered('selected')
        if not lines_selected:
            raise UserError(_("Aucune ligne sélectionnée. Cochez au moins une ligne à corriger."))

        inventories_touched = self.env['physical.inventory']
        for line in lines_selected:
            line.inventory_line_id.write({
                'quantity': line.new_quantity,
                'quantity_corrected': True,
            })
            inventories_touched |= line.inventory_physical_id

        for inventory in inventories_touched:
            inventory.message_post(
                body=_(
                    "Quantités système corrigées via l'assistant de correction "
                    "(stock au %(date)s) sur %(count)s ligne(s).",
                    date=self.date,
                    count=len(lines_selected.filtered(lambda l: l.inventory_physical_id == inventory)),
                ),
                subject=_('Correction des quantités'),
                message_type='notification',
            )

        return {'type': 'ir.actions.act_window_close'}


class PhysicalInventoryUpdateQuantityWizardLine(models.TransientModel):
    _name = 'physical.inventory.update.quantity.wizard.line'
    _description = "Ligne wizard de correction des quantités d'inventaire"

    wizard_id = fields.Many2one(
        'physical.inventory.update.quantity.wizard',
        required=True,
        ondelete='cascade',
    )
    inventory_line_id = fields.Many2one(
        'physical.inventory.line',
        string='Ligne inventaire',
        required=True,
        readonly=True,
    )
    inventory_physical_id = fields.Many2one(
        'physical.inventory',
        string='Inventaire',
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Article',
        readonly=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Emplacement',
        readonly=True,
    )
    old_quantity = fields.Float(
        string='Ancienne quantité',
        readonly=True,
        digits='Product Unit of Measure',
    )
    new_quantity = fields.Float(
        string='Nouvelle quantité',
        readonly=True,
        digits='Product Unit of Measure',
    )
    diff = fields.Float(
        string='Écart',
        compute='_compute_diff',
        digits='Product Unit of Measure',
    )
    selected = fields.Boolean(
        string='Corriger',
        default=True,
    )

    @api.depends('old_quantity', 'new_quantity')
    def _compute_diff(self):
        for line in self:
            line.diff = line.new_quantity - line.old_quantity
