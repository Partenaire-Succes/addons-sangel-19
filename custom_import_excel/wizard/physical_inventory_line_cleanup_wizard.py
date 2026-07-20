# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PhysicalInventoryLineCleanupWizard(models.TransientModel):
    _name = 'physical.inventory.line.cleanup.wizard'
    _description = "Nettoyage des lignes d'inventaire orphelines"

    state = fields.Selection([
        ('draft',   'Paramètres'),
        ('preview', 'Aperçu'),
        ('done',    'Terminé'),
    ], default='draft', readonly=True)

    company_id = fields.Many2one(
        'res.company', string="Société", required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(string="Date de début")
    date_to   = fields.Date(string="Date de fin")

    line_ids = fields.One2many(
        'physical.inventory.line.cleanup.wizard.line', 'wizard_id', string="Lignes orphelines"
    )
    count_found = fields.Integer("Lignes trouvées", compute='_compute_count_found')
    summary_html = fields.Html("Résumé", readonly=True)

    @api.depends('line_ids')
    def _compute_count_found(self):
        for rec in self:
            rec.count_found = len(rec.line_ids)

    # ------------------------------------------------------------------
    # Critère : sans parent (inventaire physique) et quantité comptée = 0
    # ------------------------------------------------------------------

    def _orphan_domain(self):
        domain = [
            ('inventory_physical_id', '=', False),
            ('physical_qty', '=', 0),
        ]
        # Ces lignes n'ont pas de parent (donc pas de company_id via
        # inventory_physical_id.company_id) : on ne peut les rattacher à une
        # société qu'à travers la visibilité produit (allowed_company_ids,
        # champ ajouté par custom_sales — pas une dépendance de ce module,
        # d'où la vérification défensive, même pattern que
        # PhysicalInventory.create_line_physical()).
        has_allowed = bool(self.env['product.template']._fields.get('allowed_company_ids'))
        if has_allowed:
            domain += [
                '|',
                ('product_tmpl_id.allowed_company_ids', '=', False),
                ('product_tmpl_id.allowed_company_ids', 'in', self.company_id.ids),
            ]
        # Période de contrôle : sur create_date (date de création native
        # Odoo de la ligne), pas sur une date métier — ces lignes orphelines
        # n'ont pas de date d'inventaire (pas de parent).
        if self.date_from:
            domain.append(('create_date', '>=', datetime.combine(self.date_from, time.min)))
        if self.date_to:
            domain.append(('create_date', '<=', datetime.combine(self.date_to, time.max)))
        return domain

    # ------------------------------------------------------------------
    # Étape 1 — Analyser
    # ------------------------------------------------------------------

    def action_preview(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError(_("La date de début doit être antérieure ou égale à la date de fin."))

        self.line_ids.unlink()

        orphan_lines = self.env['physical.inventory.line'].with_context(
            active_test=False
        ).search(self._orphan_domain())

        vals_list = [{
            'wizard_id': self.id,
            'orphan_line_id': line.id,
            'product_id': line.product_id.id,
            'product_tmpl_id': line.product_tmpl_id.id,
            'physical_qty': line.physical_qty,
            'active': line.active,
            'create_date': line.create_date,
        } for line in orphan_lines]

        if vals_list:
            self.env['physical.inventory.line.cleanup.wizard.line'].create(vals_list)

        self.state = 'preview'
        return self._reload()

    # ------------------------------------------------------------------
    # Étape 2 — Supprimer
    # ------------------------------------------------------------------

    def action_delete(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Aucune ligne à supprimer."))

        orphan_lines = self.env['physical.inventory.line'].with_context(
            active_test=False
        ).browse(self.line_ids.mapped('orphan_line_id').ids)

        # Sécurité : on ne supprime que ce qui vérifie encore le critère au
        # moment du clic (au cas où une ligne aurait été rattachée à un
        # inventaire ou recomptée entre l'aperçu et la suppression).
        orphan_lines = orphan_lines.exists().filtered(
            lambda l: not l.inventory_physical_id and not l.physical_qty
        )
        nb = len(orphan_lines)
        skipped = len(self.line_ids) - nb

        orphan_lines.unlink()
        _logger.info("[CLEANUP PHYSICAL INVENTORY LINE] %d ligne(s) orpheline(s) supprimée(s)", nb)

        self.line_ids.write({'state': 'done'})
        self.summary_html = self._build_result_html(nb, skipped)
        self.state = 'done'
        return self._reload()

    def action_reset(self):
        self.line_ids.unlink()
        self.write({'state': 'draft', 'summary_html': False})
        return self._reload()

    def _build_result_html(self, nb, skipped):
        html = f"""
        <div style="font-family:Arial,sans-serif;padding:10px;">
          <h3 style="color:#28a745;border-bottom:2px solid #28a745;padding-bottom:8px;">
            Nettoyage terminé
          </h3>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#f8f9fa;">
              <td style="padding:8px;border:1px solid #dee2e6;">Lignes supprimées</td>
              <td style="padding:8px;border:1px solid #dee2e6;font-weight:bold;">{nb}</td>
            </tr>
          </table>
        """
        if skipped:
            html += f"""
          <p style="color:#e67e22;font-weight:bold;margin-top:10px;">
            ⚠ {skipped} ligne(s) ignorée(s) : rattachées à un inventaire ou recomptées
            entre temps.
          </p>
            """
        html += "</div>"
        return html

    def _reload(self):
        return {
            'type':      'ir.actions.act_window',
            'res_model': self._name,
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'new',
        }


class PhysicalInventoryLineCleanupWizardLine(models.TransientModel):
    _name = 'physical.inventory.line.cleanup.wizard.line'
    _description = "Ligne d'inventaire orpheline à supprimer"
    _order = 'create_date desc'

    wizard_id = fields.Many2one('physical.inventory.line.cleanup.wizard', ondelete='cascade')
    orphan_line_id = fields.Many2one(
        'physical.inventory.line', string="Ligne", ondelete='set null'
    )

    product_id = fields.Many2one('product.product', string="Produit", readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string="Modèle produit", readonly=True)
    physical_qty = fields.Float("Qté comptée", digits=(16, 3), readonly=True)
    active = fields.Boolean("Active", readonly=True)
    create_date = fields.Datetime("Créée le", readonly=True)

    state = fields.Selection([
        ('preview', 'À supprimer'),
        ('done',    'Supprimée'),
    ], default='preview', readonly=True)
