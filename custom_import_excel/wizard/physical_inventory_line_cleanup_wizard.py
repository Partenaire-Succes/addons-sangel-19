# -*- coding: utf-8 -*-
import logging

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
        return [
            ('inventory_physical_id', '=', False),
            ('physical_qty', '=', 0),
        ]

    # ------------------------------------------------------------------
    # Étape 1 — Analyser
    # ------------------------------------------------------------------

    def action_preview(self):
        self.ensure_one()
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
