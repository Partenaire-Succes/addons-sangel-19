# -*- coding: utf-8 -*-
import base64
import io
from odoo import fields, models, api
from datetime import date
from collections import defaultdict


class CadencierWizard(models.TransientModel):
    _name = 'cadencier.ventes.wizard'
    _description = 'Wizard Cadencier Stat Ventes Articles'

    year = fields.Selection(
        selection='_get_years',
        string="Année",
        required=True,
        default=lambda self: str(date.today().year),
    )
    company_id = fields.Many2one(
        'res.company',
        string="Société",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )
    famille_ids = fields.Many2many(
        'product.category',
        string="Familles (optionnel)",
        help="Laisser vide pour toutes les familles",
    )

    @api.model
    def _get_years(self):
        current_year = date.today().year
        return [(str(y), str(y)) for y in range(current_year - 5, current_year + 2)]

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('custom_reports.action_report_cadencier').report_action(self)

    # ─────────────────────────────────────────────────────────────
    # EXPORT EXCEL
    # ─────────────────────────────────────────────────────────────
    def action_export_excel(self):
        """Génère le cadencier au format Excel et le retourne en téléchargement."""
        self.ensure_one()
        try:
            from openpyxl import Workbook
            from openpyxl.styles import (
                Font, PatternFill, Alignment, Border, Side, numbers
            )
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise UserError("La bibliothèque openpyxl est requise. Installez-la via : pip install openpyxl")

        lines = self._get_report_data(
            self.year,
            self.company_id.id,
            self.famille_ids.ids,
        )

        wb = Workbook()
        ws = wb.active
        ws.title = f"Cadencier {self.year}"

        # ── Couleurs ──────────────────────────────────────────────
        COLOR_DARK   = "1A1A2E"
        COLOR_CYAN   = "00C8E0"
        COLOR_ORANGE = "FF6B35"
        COLOR_GREY   = "C1B7B7"
        COLOR_LIGHT  = "D9F5F8"
        COLOR_TOTAL  = "FFF3EE"
        COLOR_SUB_BG = "0A3D4D"
        COLOR_WHITE  = "FFFFFF"

        thin = Side(style='thin', color=COLOR_DARK)
        border_all = Border(left=thin, right=thin, top=thin, bottom=thin)

        def fill(hex_color):
            return PatternFill("solid", fgColor=hex_color)

        def font(bold=False, color=COLOR_DARK, size=9):
            return Font(name="Arial", bold=bold, color=color, size=size)

        def align(h="center", v="center", wrap=False):
            return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

        # ── Ligne 1 : titre société ────────────────────────────────
        ws.merge_cells("A1:U1")
        company = self.company_id
        ws["A1"] = (
            f"{company.name}"
            + (f"  –  {company.street}" if company.street else "")
            + (f", {company.city}" if company.city else "")
        )
        ws["A1"].font = font(bold=True, size=10)
        ws["A1"].alignment = align(h="left")

        # ── Ligne 2 : titre rapport ────────────────────────────────
        ws.merge_cells("A2:U2")
        ws["A2"] = (
            f"CADENCIER STAT VENTES ARTICLES  –  ANNEE {self.year}  –  SOURCE : POS + MODULE VENTE"
        )
        ws["A2"].font = font(bold=True, color=COLOR_WHITE, size=12)
        ws["A2"].fill = fill(COLOR_DARK)
        ws["A2"].alignment = align()

        ws.row_dimensions[2].height = 20

        # ── Ligne 3 vide ───────────────────────────────────────────
        ws.append([])

        # ── En-têtes colonnes (ligne 4) ────────────────────────────
        MONTHS = ['JAN', 'FEV', 'MAR', 'AVR', 'MAI', 'JUIN',
                  'JLT', 'AOT', 'SPT', 'OCT', 'NOV', 'DEC']
        headers = ['CODE', 'DESIGNATION', 'STA.', 'FAMILLE',
                   'ST.DISP.', 'MAXI', 'CMD', 'MARG%', 'PVTC'] + MONTHS + ['TOTAL']

        header_row = 4
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=header)
            cell.font = font(bold=True, color=COLOR_WHITE, size=9)
            cell.alignment = align()
            cell.border = border_all
            # Mois en cyan, TOTAL en orange, reste en dark
            if header in MONTHS:
                cell.fill = fill(COLOR_CYAN)
                cell.font = font(bold=True, color=COLOR_DARK, size=9)
            elif header == 'TOTAL':
                cell.fill = fill(COLOR_ORANGE)
            else:
                cell.fill = fill(COLOR_DARK)

        ws.row_dimensions[header_row].height = 18

        # ── Données ────────────────────────────────────────────────
        data_start_row = 5
        for row_offset, line in enumerate(lines):
            r = data_start_row + row_offset

            if line.get('is_subtotal'):
                # ── Sous-total famille ─────────────────────────────
                label = f"▶ TOTAL  {line['code_famille']} — {line['famille']}"
                ws.merge_cells(f"A{r}:D{r}")
                ws[f"A{r}"] = label
                ws[f"A{r}"].font = font(bold=True, size=9)
                ws[f"A{r}"].fill = fill(COLOR_GREY)
                ws[f"A{r}"].alignment = align(h="left")
                ws[f"A{r}"].border = border_all

                # Colonnes ST.DISP … PVTC vides
                for c in range(5, 10):
                    cell = ws.cell(row=r, column=c)
                    cell.fill = fill(COLOR_GREY)
                    cell.border = border_all

                # Ventes mensuelles
                for m_idx, qty in enumerate(line['ventes']):
                    c = 10 + m_idx
                    cell = ws.cell(row=r, column=c)
                    cell.value = qty if qty > 0 else None
                    cell.font = font(bold=True, color=COLOR_CYAN if qty > 0 else COLOR_DARK, size=9)
                    cell.fill = fill(COLOR_SUB_BG if qty > 0 else COLOR_GREY)
                    cell.alignment = align()
                    cell.border = border_all
                    cell.number_format = '#,##0'

                # Total
                cell_total = ws.cell(row=r, column=22)
                cell_total.value = line['total']
                cell_total.font = font(bold=True, color=COLOR_WHITE, size=9)
                cell_total.fill = fill(COLOR_ORANGE)
                cell_total.alignment = align()
                cell_total.border = border_all
                cell_total.number_format = '#,##0'

                ws.row_dimensions[r].height = 16

            else:
                # ── Ligne produit ──────────────────────────────────
                row_values = [
                    line['code'],
                    line['designation'],
                    line['sta'],
                    line['famille'],
                    line['st_disp'],
                    line['maxi'],
                    line['cmd'],
                    line['marg'],
                    line['pvtc'],
                ] + [v if v > 0 else 0 for v in line['ventes']] + [line['total']]

                for col_idx, value in enumerate(row_values, start=1):
                    cell = ws.cell(row=r, column=col_idx, value=value)
                    cell.font = font(size=9)
                    cell.border = border_all
                    cell.alignment = align(h="left" if col_idx == 2 else "center", wrap=(col_idx == 2))

                    # Formatage spécifique par colonne
                    if col_idx == 9:                         # PVTC
                        cell.number_format = '#,##0'
                    elif col_idx == 8:                       # MARG%
                        cell.number_format = '0.00"%"'
                    elif col_idx in range(10, 22):           # Mois
                        cell.number_format = '#,##0'
                        if value and value > 0:
                            cell.fill = fill(COLOR_LIGHT)
                            cell.font = font(bold=True, size=9)
                    elif col_idx == 22:                      # TOTAL
                        cell.number_format = '#,##0'
                        if line['total'] > 0:
                            cell.fill = fill(COLOR_TOTAL)
                            cell.font = font(bold=True, color=COLOR_ORANGE, size=9)

                ws.row_dimensions[r].height = 15

        # ── Largeurs de colonnes ───────────────────────────────────
        col_widths = [
            9,   # CODE
            28,  # DESIGNATION
            5,   # STA
            14,  # FAMILLE
            8,   # ST.DISP
            7,   # MAXI
            7,   # CMD
            7,   # MARG
            12,  # PVTC
        ] + [7] * 12 + [9]   # Mois + TOTAL

        for i, width in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width

        # Figer les 4 premières colonnes et la ligne d'en-tête
        ws.freeze_panes = "E5"

        # ── Sauvegarde en mémoire ──────────────────────────────────
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        xlsx_data = base64.b64encode(buffer.read()).decode()

        filename = f"Cadencier_Ventes_{self.year}.xlsx"

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    # ─────────────────────────────────────────────────────────────
    # DONNÉES RAPPORT
    # ─────────────────────────────────────────────────────────────
    def _get_report_data(self, year, company_id, famille_ids=None):
        company = self.env['res.company'].browse(company_id)
        date_from = date(int(year), 1, 1)
        date_to = date(int(year), 12, 31)
        product_data = defaultdict(lambda: defaultdict(float))

        products = self.env['product.template'].search([
            ('allowed_company_ids', 'in', company_id),
            ('type', '=', 'consu'),
            ('active', '=', True),
            ('cat_gestion_id.name', 'in', ['01', '02', '04', '05', '06', 'DI'])
        ])

        final_products = self.env['product.template']

        for p in products:
            if p.current_company_status_id and p.current_company_status_id.code == 'C':
                final_products |= p
            else:
                if any(v.qty_available > 0 for v in p.product_variant_ids):
                    final_products |= p

        for p in final_products:
            for variant in p.product_variant_ids:
                product_data[variant.id]

        sale_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.company_id', '=', company_id),
            ('product_id.type', '=', 'consu'),
            ('order_id.date_order', '>=', str(date_from)),
            ('order_id.date_order', '<=', str(date_to)),
            ('product_id.active', '=', True),
        ]
        sale_lines = self.env['sale.order.line'].search(sale_domain)

        pos_domain = [
            ('order_id.state', 'in', ['done', 'paid', 'invoiced']),
            ('order_id.company_id', '=', company_id),
            ('product_id.type', '=', 'consu'),
            ('order_id.date_order', '>=', str(date_from)),
            ('order_id.date_order', '<=', str(date_to)),
            ('product_id.active', '=', True),
        ]
        pos_lines = self.env['pos.order.line'].search(pos_domain)

        for line in sale_lines:
            month_idx = line.order_id.date_order.month - 1
            product_data[line.product_id.id][month_idx] += line.product_uom_qty

        for line in pos_lines:
            month_idx = line.order_id.date_order.month - 1
            product_data[line.product_id.id][month_idx] += line.qty

        if not product_data:
            return []

        product_ids = list(product_data.keys())
        products = self.env['product.product'].browse(product_ids)

        if famille_ids:
            products = products.filtered(
                lambda p: p.categ_id.id in famille_ids
            )

        result = []
        for product in products.sorted(key=lambda p: ((p.categ_id.code or '').lower(), (p.default_code or '').lower())):
            monthly_qtys = product_data[product.id]
            ventes = [round(monthly_qtys.get(i, 0), 2) for i in range(12)]
            total = sum(ventes)
            stock = product.with_company(company).qty_available
            pmp = product.avg_cost if product.avg_cost else product.standard_price

            total_ca = 0.0
            for line in sale_lines:
                if line.product_id.id == product.id:
                    total_ca += line.price_subtotal

            for line in pos_lines:
                if line.product_id.id == product.id:
                    total_ca += line.price_subtotal

            total_cost = total * pmp
            taux_marge = round((total_ca - total_cost) / total_ca * 100, 2) if total_ca > 0 else 0.0

            taxes = product.taxes_id.compute_all(
                product.list_price,
                currency=product.currency_id,
                quantity=1,
                product=product,
                partner=None,
            )
            price_ttc = taxes['total_included']

            result.append({
                'code': product.default_code or '',
                'designation': product.name,
                'sta': product.current_company_status_id.code if product.current_company_status_id else '',
                'maxi': product.max_qty_orderpoint,
                'cmd': product.pending_reception_qty,
                'marg': taux_marge,
                'famille': product.categ_id.name,
                'code_famille': product.categ_id.code,
                'st_disp': round(stock, 2),
                'pvtc': price_ttc,
                'ventes': ventes,
                'total': total,
            })

        final_result = []
        current_famille_code = None
        famille_ventes = [0.0] * 12
        famille_total = 0.0
        famille_label = ''

        for item in result:
            item['is_subtotal'] = False
            if current_famille_code is not None and item['code_famille'] != current_famille_code:
                final_result.append({
                    'is_subtotal': True,
                    'famille': famille_label,
                    'code_famille': current_famille_code,
                    'ventes': [round(v, 2) for v in famille_ventes],
                    'total': round(famille_total, 2),
                })
                famille_ventes = [0.0] * 12
                famille_total = 0.0

            current_famille_code = item['code_famille']
            famille_label = item['famille']
            final_result.append(item)
            for i in range(12):
                famille_ventes[i] += item['ventes'][i]
            famille_total += item['total']

        if current_famille_code is not None:
            final_result.append({
                'is_subtotal': True,
                'famille': famille_label,
                'code_famille': current_famille_code,
                'ventes': [round(v, 2) for v in famille_ventes],
                'total': round(famille_total, 2),
            })

        return final_result


class ReportCadencierVentes(models.AbstractModel):
    _name = 'report.custom_reports.report_cadencier_template'
    _description = 'Rapport Cadencier Ventes'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['cadencier.ventes.wizard'].browse(docids)
        lines = wizard._get_report_data(
            wizard.year,
            wizard.company_id.id,
            wizard.famille_ids.ids,
        )
        return {
            'doc': wizard,
            'company': wizard.company_id,
            'year': wizard.year,
            'lines': lines,
        }