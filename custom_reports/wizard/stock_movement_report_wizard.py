# -*- coding: utf-8 -*-
import io
import base64

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import float_round


class StockMovementReportWizard(models.TransientModel):
    _name = 'stock.movement.report.wizard'
    _description = 'Rapport Stock et Mouvements entre deux dates'

    date_from = fields.Datetime(
        string='Date A',
        required=True,
        default=fields.Datetime.now,
        help="Stock reconstitué à cet instant précis.",
    )
    date_to = fields.Datetime(
        string='Date B',
        required=True,
        default=fields.Datetime.now,
        help="Stock reconstitué à cet instant précis.",
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Emplacement',
        required=True,
        domain=[('usage', '=', 'internal')],
    )
    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
    )
    category_ids = fields.Many2many(
        'product.category.x3',
        string='Niveau 5',
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from > record.date_to:
                raise UserError("La Date A doit être antérieure ou égale à la Date B.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'location_id' in fields_list and not res.get('location_id'):
            location = self.env['stock.location'].search([
                ('usage', '=', 'internal'),
                '|',
                ('name', 'ilike', 'Stock'),
                ('complete_name', 'ilike', '/Stock'),
            ], limit=1)
            if not location:
                warehouse = self.env['stock.warehouse'].search([
                    ('company_id', '=', self.env.company.id),
                ], limit=1)
                if warehouse:
                    location = warehouse.lot_stock_id
            if location:
                res['location_id'] = location.id
        return res

    # -------------------------------------------------------------------------
    # LOGIQUE DU RAPPORT
    # -------------------------------------------------------------------------
    def _get_products(self):
        self.ensure_one()
        domain = [
            ('product_tmpl_id.allowed_company_ids', 'in', [self.company_id.id]),
            ('product_tmpl_id.type', '=', 'consu'),
            ('product_tmpl_id.prod_type_x3_id.name', '=', 'TS'),
        ]
        if self.category_ids:
            domain.append(('cat_gestion_id', 'in', self.category_ids.ids))
        return self.env['product.product'].search(domain)

    def _get_stock_at(self, product_ids, at):
        """Reconstitue le stock à l'instant `at` pour `product_ids`, à
        l'emplacement sélectionné, à partir des stock.move.line validées."""
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
        """, [self.location_id.id, list(product_ids), at, self.location_id.id, self.location_id.id])
        return {row[0]: row[1] for row in self.env.cr.fetchall()}

    def _get_movements(self, product_ids):
        """Mouvements nets (entrées - sorties) entre Date A (exclue) et Date B
        (incluse), à l'emplacement sélectionné."""
        if not product_ids:
            return {}
        self.env.cr.execute("""
            SELECT product_id,
                   SUM(CASE WHEN location_dest_id = %s THEN quantity ELSE -quantity END) AS mvt
            FROM stock_move_line
            WHERE product_id = ANY(%s)
              AND state = 'done'
              AND date > %s
              AND date <= %s
              AND (location_id = %s OR location_dest_id = %s)
            GROUP BY product_id
        """, [self.location_id.id, list(product_ids), self.date_from, self.date_to, self.location_id.id, self.location_id.id])
        return {row[0]: row[1] for row in self.env.cr.fetchall()}

    def _get_cumulative_gap(self, product_ids):
        """Écart cumulé : somme de tous les qty_diff des lignes d'inventaire
        physique journalier validées (toutes dates confondues) par produit."""
        if not product_ids:
            return {}
        groups = self.env['physical.inventory.line'].read_group(
            domain=[
                ('product_id', 'in', product_ids),
                ('company_id', '=', self.company_id.id),
                ('active', '=', True),
                ('state', '=', 'done'),
            ],
            fields=['qty_diff:sum'],
            groupby=['product_id'],
        )
        return {g['product_id'][0]: g['qty_diff'] for g in groups}

    def _get_report_lines(self):
        self.ensure_one()
        products = self._get_products()
        product_ids = products.ids

        stock_a = self._get_stock_at(product_ids, self.date_from)
        stock_b = self._get_stock_at(product_ids, self.date_to)
        movements = self._get_movements(product_ids)
        cumulative_gap = self._get_cumulative_gap(product_ids)

        lines = []
        for product in products:
            qty_a = stock_a.get(product.id, 0.0)
            qty_b = stock_b.get(product.id, 0.0)
            mvt = movements.get(product.id, 0.0)
            gap = cumulative_gap.get(product.id, 0.0)

            if not qty_a and not qty_b and not mvt and not gap:
                continue

            lines.append({
                'code_article': product.code_article or product.product_tmpl_id.code_article or '',
                'name': product.name,
                'cost': float_round(product.with_company(self.company_id).standard_price or 0.0, 2),
                'stock_a': float_round(qty_a, 2),
                'stock_b': float_round(qty_b, 2),
                'movement': float_round(mvt, 2),
                'ecart_cumule': float_round(gap, 2),
            })

        return sorted(lines, key=lambda l: l['code_article'])

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    def action_print_report(self):
        self.ensure_one()
        report_action = self.env.ref('custom_reports.action_report_stock_movement').report_action(self)
        report_action['close_on_report_download'] = True
        return report_action

    def action_export_excel(self):
        self.ensure_one()
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            raise UserError("La bibliothèque openpyxl est requise.")

        lines = self._get_report_lines()
        if not lines:
            raise UserError("Aucune donnée trouvée pour la période sélectionnée.")

        wb = Workbook()
        ws = wb.active
        ws.title = "Stock et Mouvements"

        BLUE = "1A5276"; WHITE = "FFFFFF"
        thin = Side(style='thin', color="AAAAAA")
        brd = Border(left=thin, right=thin, top=thin, bottom=thin)
        def fill(h): return PatternFill("solid", fgColor=h)
        def aln(h="left"): return Alignment(horizontal=h, vertical="center")

        ws.merge_cells("A1:G1")
        ws["A1"] = self.company_id.name
        ws["A1"].font = Font(name="Arial", bold=True, size=11)

        ws.merge_cells("A2:G2")
        ws["A2"] = (
            f"STOCK ET MOUVEMENTS — {self.location_id.complete_name} — "
            f"{self.date_from.strftime('%d/%m/%Y %H:%M')} au {self.date_to.strftime('%d/%m/%Y %H:%M')}"
        )
        ws["A2"].font = Font(name="Arial", bold=True, color=WHITE, size=11)
        ws["A2"].fill = fill(BLUE)
        ws["A2"].alignment = aln("center")
        ws.row_dimensions[2].height = 18
        ws.append([])

        headers = [
            "Code Article", "Nom produit", "Coût",
            f"Stock {self.date_from.strftime('%d/%m/%Y %H:%M')}",
            f"Stock {self.date_to.strftime('%d/%m/%Y %H:%M')}",
            "Mvts (Entrée-Sortie)",
            "Ecart cumulé",
        ]
        ws.append(headers)
        hrow = ws.max_row
        for col in range(1, 8):
            c = ws.cell(row=hrow, column=col)
            c.font = Font(name="Arial", bold=True, color=WHITE, size=10)
            c.fill = fill(BLUE); c.alignment = aln("center"); c.border = brd

        for line in lines:
            ws.append([
                line['code_article'], line['name'], line['cost'],
                line['stock_a'], line['stock_b'], line['movement'], line['ecart_cumule'],
            ])
            r = ws.max_row
            for col in range(1, 8):
                c = ws.cell(row=r, column=col)
                c.font = Font(name="Arial", size=9); c.border = brd
                c.alignment = aln("right" if col >= 3 else "left")
            for col in (3, 4, 5, 6, 7):
                ws.cell(row=r, column=col).number_format = '#,##0.00'

        for col, width in enumerate([14, 34, 14, 20, 20, 18, 14], 1):
            ws.column_dimensions[chr(64 + col)].width = width

        buffer = io.BytesIO(); wb.save(buffer); buffer.seek(0)
        xlsx_data = base64.b64encode(buffer.read()).decode()
        filename = (
            f"Stock_Mouvements_{self.date_from.strftime('%Y%m%d_%Hh%M')}_"
            f"{self.date_to.strftime('%Y%m%d_%Hh%M')}.xlsx"
        )
        attachment = self.env['ir.attachment'].create({
            'name': filename, 'type': 'binary', 'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name, 'res_id': self.id,
        })
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true', 'target': 'new'}
