# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


class StockAvcoCorrectionWizard(models.TransientModel):
    _name = 'stock.avco.correction.wizard'
    _description = 'Correction AVCO - Réceptions à Valeur Zéro'

    company_id      = fields.Many2one(
        'res.company', string='Société', required=True,
        default=lambda self: self.env.company,
    )
    import_file     = fields.Binary(string='Fichier Excel (Code Article | Prix Correct)',
                                    attachment=False)
    import_filename = fields.Char(string='Nom du fichier')
    state           = fields.Selection([
        ('draft',   'Import'),
        ('preview', 'Aperçu'),
        ('done',    'Terminé'),
    ], default='draft', readonly=True)

    line_ids     = fields.One2many('stock.avco.correction.line', 'wizard_id', string='Lignes')
    count_ok     = fields.Integer(compute='_compute_stats')
    count_warning= fields.Integer(compute='_compute_stats')
    count_error  = fields.Integer(compute='_compute_stats')
    total_value  = fields.Float(compute='_compute_stats', string='Valeur totale à injecter')
    can_validate = fields.Boolean(compute='_compute_stats')
    result_log   = fields.Html(string='Rapport', readonly=True)

    @api.depends('line_ids.line_state', 'line_ids.value_to_inject')
    def _compute_stats(self):
        for rec in self:
            ok             = rec.line_ids.filtered(lambda l: l.line_state == 'ok')
            rec.count_ok      = len(ok)
            rec.count_warning = len(rec.line_ids.filtered(lambda l: l.line_state == 'warning'))
            rec.count_error   = len(rec.line_ids.filtered(lambda l: l.line_state == 'error'))
            rec.total_value   = sum(ok.mapped('value_to_inject'))
            rec.can_validate  = bool(ok)

    # ── Étape 1 : Analyser ───────────────────────────────────────────────────

    def action_preview(self):
        self.ensure_one()
        if not OPENPYXL_AVAILABLE:
            raise UserError(_("openpyxl non installé. pip install openpyxl"))
        if not self.import_file:
            raise UserError(_("Veuillez sélectionner un fichier Excel."))

        self.line_ids.unlink()
        rows       = self._read_excel()
        lines_vals = [self._compute_line(code, price) for code, price in rows]

        if lines_vals:
            self.env['stock.avco.correction.line'].create(lines_vals)

        self.write({'state': 'preview'})
        return self._reload()

    def _read_excel(self):
        """Lit le fichier Excel → [(code_article, prix_correct), ...]"""
        data = base64.b64decode(self.import_file)
        wb   = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        ws   = wb.active
        rows = []

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            code = str(row[0]).strip()
            if code.endswith('.0'):
                code = code[:-2]
            code = code.zfill(4)
            try:
                price = float(row[1]) if len(row) > 1 and row[1] is not None else 0.0
            except (ValueError, TypeError):
                price = 0.0
            if code:
                rows.append((code, price))

        if not rows:
            raise UserError(_(
                "Aucune donnée trouvée.\n"
                "Format attendu : Colonne A = Code Article | Colonne B = Prix Correct\n"
                "Données à partir de la ligne 2."
            ))
        return rows

    def _compute_line(self, code, correct_price):
        """Calcule les données de correction pour un produit via stock.move."""
        base = {'wizard_id': self.id, 'default_code': code, 'correct_price': correct_price}

        # ── 1. Produit ───────────────────────────────────────────────────────
        product = self.env['product.product'].search(
            [('default_code', '=', code), ('active', '=', True)], limit=1)
        if not product:
            return {**base, 'line_state': 'error',
                    'message': f"Article '{code}' introuvable dans Odoo."}

        base.update({'product_id': product.id, 'product_name': product.display_name})

        if correct_price <= 0:
            return {**base, 'line_state': 'error',
                    'message': "Le prix correct doit être supérieur à 0."}

        # ── 2. Mouvements entrants à valeur zéro ─────────────────────────────
        zero_moves = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('company_id', '=', self.company_id.id),
            ('is_in',      '=', True),
            ('state',      '=', 'done'),
            ('value',      '=', 0),
            ('quantity',   '>',  0),
        ])
        if not zero_moves:
            return {**base, 'line_state': 'warning',
                    'message': "Aucune réception à valeur zéro trouvée pour cet article."}

        # ── 3. AVCO actuel (calculé depuis tous les moves entrants) ───────────
        all_in_moves = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('company_id', '=', self.company_id.id),
            ('is_in',      '=', True),
            ('state',      '=', 'done'),
        ])
        total_qty_in   = sum(all_in_moves.mapped('quantity'))
        total_value_in = sum(all_in_moves.mapped('value'))
        current_avco   = round(total_value_in / total_qty_in, 4) if total_qty_in else 0.0

        # ── 4. Correction ────────────────────────────────────────────────────
        qty_zero     = sum(zero_moves.mapped('quantity'))
        value_inject = round(qty_zero * correct_price, 2)
        new_avco     = round((total_value_in + value_inject) / total_qty_in, 6) \
                       if total_qty_in else correct_price

        return {
            **base,
            'qty_zero_svl':    qty_zero,
            'value_to_inject': value_inject,
            'current_avco':    current_avco,
            'current_qty':     total_qty_in,
            'new_avco':        new_avco,
            'line_state':      'ok',
            'message':         '',
        }

    # ── Étape 2 : Corriger ───────────────────────────────────────────────────

    def action_validate(self):
        self.ensure_one()
        ok_lines = self.line_ids.filtered(lambda l: l.line_state == 'ok')
        if not ok_lines:
            raise UserError(_("Aucune ligne valide à corriger."))

        corrected      = 0
        errors         = 0
        total_injected = 0.0
        error_msgs     = []

        for line in ok_lines:
            try:
                # Récupère les moves à zéro pour ce produit/société
                zero_moves = self.env['stock.move'].search([
                    ('product_id', '=', line.product_id.id),
                    ('company_id', '=', self.company_id.id),
                    ('is_in',      '=', True),
                    ('state',      '=', 'done'),
                    ('value',      '=', 0),
                    ('quantity',   '>',  0),
                ])

                # Corrige chaque move à zéro
                for move in zero_moves:
                    correct_value = move.quantity * line.correct_price
                    move.write({
                        'price_unit': line.correct_price,
                        'value':      correct_value,
                    })

                # Met à jour le standard_price (AVCO courant du produit)
                line.product_id.with_company(self.company_id).write({
                    'standard_price': line.new_avco,
                })

                total_injected += line.value_to_inject
                corrected      += 1
                _logger.info(
                    "[AVCO CORRECTION] %s : AVCO %.4f → %.4f (valeur injectée %.2f)",
                    line.default_code, line.current_avco,
                    line.new_avco, line.value_to_inject,
                )
            except Exception as e:
                errors += 1
                error_msgs.append(f"{line.default_code} : {str(e)}")
                _logger.exception("Erreur correction AVCO %s", line.default_code)

        self.write({
            'state':      'done',
            'result_log': self._build_log(corrected, errors, total_injected, error_msgs),
        })
        return self._reload()

    def action_back_to_draft(self):
        self.line_ids.unlink()
        self.write({'state': 'draft'})
        return self._reload()

    def _build_log(self, corrected, errors, total_injected, error_msgs):
        red  = "#C00000"
        html = (
            f"<div style='font-family:Arial,sans-serif;font-size:13px;'>"
            f"<p>✅ <b>{corrected}</b> article(s) corrigé(s)</p>"
            f"<p>💰 Valeur totale injectée : <b>{total_injected:,.2f}</b></p>"
        )
        if error_msgs:
            html += (
                f"<p style='color:{red};'><b>❌ {errors} erreur(s) :</b></p><ul>"
                + "".join(f"<li style='color:{red};'>{m}</li>" for m in error_msgs)
                + "</ul>"
        )
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
