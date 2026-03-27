# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class RetoursConsolidesReportWizard(models.TransientModel):
    """
    BLOC 6 — Rapport consolidé des retours et réceptions internes.

    Couvre :
      - Réceptions directes (BLOC 2) avec prix de réception et prix mis à jour.
      - Retours fournisseurs (BLOC 5) : pickings incoming inversés (stock → fournisseur).
      - Retours inventaires (BLOC 4) : avoirs fournisseurs générés depuis l'inventaire.
    """
    _name = 'retours.consolides.report.wizard'
    _description = 'Rapport Consolidé Retours et Réceptions'

    date_from = fields.Date(
        string='Date de début',
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(
        string='Date de fin',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise UserError("La date de début doit être antérieure à la date de fin.")

    # ────────────────────────────────────────────────────────────────────────
    # DONNÉES RAPPORT
    # ────────────────────────────────────────────────────────────────────────

    # ────────────────────────────────────────────────────────────────────────
    # HELPERS FORMAT
    # ────────────────────────────────────────────────────────────────────────
    def _fmt_date(self, d):
        if not d:
            return '—'
        if hasattr(d, 'strftime'):
            return d.strftime('%d/%m/%Y')
        return str(d)

    def _fmt_amount(self, amount):
        symbol = self.company_id.currency_id.symbol or ''
        return '%.2f %s' % (amount, symbol)

    # ────────────────────────────────────────────────────────────────────────
    # DONNÉES RAPPORT
    # ────────────────────────────────────────────────────────────────────────

    def _get_receptions_directes(self):
        """Réceptions sans BdC (BLOC 2) — prix gravé sur le stock.move (historique réel)."""
        pickings = self.env['stock.picking'].search([
            ('state', '=', 'done'),
            ('origin', '=', 'Réception Directe'),
            ('date_done', '>=', self.date_from),
            ('date_done', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ], order='date_done')

        rows = []
        for picking in pickings:
            for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                tmpl = move.product_id.product_tmpl_id
                prix_standard = tmpl.standard_price
                # move.price_unit = coût gravé lors de la réception (nouveau prix si modifié)
                prix_reception = move.price_unit
                a_nouveau_prix = (
                    prix_reception > 0
                    and abs(prix_reception - prix_standard) > 0.001
                )
                qty_done = sum(move.move_line_ids.mapped('quantity')) or move.product_uom_qty
                rows.append({
                    'date': self._fmt_date(picking.date_done),
                    'reference': picking.name,
                    'fournisseur': picking.partner_id.name or '—',
                    'notes': picking.note or '—',
                    'produit': move.product_id.display_name,
                    'qty': qty_done,
                    'uom': move.product_uom.name,
                    'prix_standard': prix_standard,
                    'prix_reception': prix_reception,
                    'a_nouveau_prix': a_nouveau_prix,
                    'montant': qty_done * prix_reception,
                })
        return rows

    def _get_retours_fournisseur(self):
        """Retours fournisseurs (BLOC 5) : stock → fournisseur."""
        pickings = self.env['stock.picking'].search([
            ('state', '=', 'done'),
            ('picking_type_code', '=', 'incoming'),
            ('location_id.usage', '=', 'internal'),
            ('location_dest_id.usage', '=', 'supplier'),
            ('date_done', '>=', self.date_from),
            ('date_done', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ], order='date_done')

        rows = []
        for picking in pickings:
            for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                qty_done = sum(move.move_line_ids.mapped('quantity')) or move.product_uom_qty
                montant = qty_done * move.price_unit
                rows.append({
                    'date': self._fmt_date(picking.date_done),
                    'reference': picking.name,
                    'origine': picking.origin or '—',
                    'fournisseur': picking.partner_id.name or '—',
                    'produit': move.product_id.display_name,
                    'qty': qty_done,
                    'uom': move.product_uom.name,
                    'prix_unitaire': move.price_unit,
                    'montant': montant,
                })
        return rows

    def _get_retours_inventaire(self):
        """Retours inventaires (BLOC 4) : avoirs fournisseurs issus d'inventaires physiques."""
        avoirs = self.env['account.move'].search([
            ('move_type', '=', 'in_refund'),
            ('state', '!=', 'cancel'),
            ('ref', 'like', 'Retour inventaire%'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ], order='invoice_date')

        etat_labels = {
            'draft': 'Brouillon',
            'posted': 'Validé',
            'cancel': 'Annulé',
        }
        rows = []
        for avoir in avoirs:
            for line in avoir.invoice_line_ids.filtered(lambda l: not l.display_type):
                rows.append({
                    'date': self._fmt_date(avoir.invoice_date),
                    'reference': avoir.name or '—',
                    'origine': avoir.ref or '—',
                    'fournisseur': avoir.partner_id.name or '—',
                    'produit': line.product_id.display_name if line.product_id else line.name,
                    'qty': line.quantity,
                    'prix_unitaire': line.price_unit,
                    'montant': line.price_subtotal,
                    'etat': etat_labels.get(avoir.state, avoir.state),
                    'etat_code': avoir.state,
                })
        return rows

    def _get_report_data(self):
        """Structure complète des données pour le template QWeb."""
        receptions = self._get_receptions_directes()
        retours_four = self._get_retours_fournisseur()
        retours_inv = self._get_retours_inventaire()

        total_receptions = sum(r['montant'] for r in receptions)
        total_retours_four = sum(r['montant'] for r in retours_four)
        total_retours_inv = sum(r['montant'] for r in retours_inv)
        grand_total = total_receptions + total_retours_four + total_retours_inv

        currency = self.company_id.currency_id

        return {
            'date_from': self._fmt_date(self.date_from),
            'date_to': self._fmt_date(self.date_to),
            'company': self.company_id,
            'currency': currency,
            'receptions_directes': receptions,
            'retours_fournisseur': retours_four,
            'retours_inventaire': retours_inv,
            'total_receptions': total_receptions,
            'total_retours_four': total_retours_four,
            'total_retours_inv': total_retours_inv,
            'grand_total': grand_total,
            'fmt': self._fmt_amount,
        }

    # ────────────────────────────────────────────────────────────────────────
    # ACTION
    # ────────────────────────────────────────────────────────────────────────

    def action_print_report(self):
        self.ensure_one()
        # Validation : vérifier qu'il y a des données
        data = self._get_report_data()
        total_lines = (
            len(data['receptions_directes'])
            + len(data['retours_fournisseur'])
            + len(data['retours_inventaire'])
        )
        if not total_lines:
            raise UserError(
                "Aucune opération trouvée pour la période et la société sélectionnées."
            )
        return self.env.ref(
            'custom_reports.action_report_retours_consolides'
        ).report_action(self)
