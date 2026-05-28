# -*- coding: utf-8 -*-
import io
import base64
from odoo import models, fields, api
from odoo.exceptions import UserError


class AchatProduitReportWizard(models.TransientModel):
    _name = 'achat.produit.report.wizard'
    _description = 'Rapport Commandes & Réceptions par Produit'

    date_debut = fields.Date(
        string='Date de début',
        required=True,
        default=fields.Date.context_today,
    )
    date_fin = fields.Date(
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
    fournisseur_ids = fields.Many2many(
        'res.partner',
        string='Fournisseurs',
        domain=[('supplier_rank', '>', 0)],
        help='Laissez vide pour inclure tous les fournisseurs',
    )

    @api.constrains('date_debut', 'date_fin')
    def _check_dates(self):
        for rec in self:
            if rec.date_debut > rec.date_fin:
                raise UserError("La date de début doit être antérieure à la date de fin.")

    def _get_report_data(self):
        """Regroupe commandes d'achat confirmées et réceptions validées par produit."""
        self.ensure_one()

        # ── Lignes de commandes d'achat confirmées / clôturées ────────────────
        po_domain = [
            ('order_id.state', 'in', ['purchase', 'done']),
            ('order_id.date_order', '>=', str(self.date_debut) + ' 00:00:00'),
            ('order_id.date_order', '<=', str(self.date_fin) + ' 23:59:59'),
            ('order_id.company_id', '=', self.company_id.id),
        ]
        if self.fournisseur_ids:
            po_domain.append(('order_id.partner_id', 'in', self.fournisseur_ids.ids))

        po_lines = self.env['purchase.order.line'].search(po_domain)

        # ── Mouvements de stock des réceptions validées ───────────────────────
        move_domain = [
            ('picking_id.picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
            ('picking_id.date_done', '>=', self.date_debut),
            ('picking_id.date_done', '<=', self.date_fin),
            ('picking_id.company_id', '=', self.company_id.id),
            ('location_id.usage', 'in', ['supplier', 'transit']),
        ]
        if self.fournisseur_ids:
            move_domain.append(('picking_id.partner_id', 'in', self.fournisseur_ids.ids))

        moves = self.env['stock.move'].search(move_domain)

        if not po_lines and not moves:
            raise UserError("Aucune donnée trouvée pour la période et les filtres sélectionnés.")

        products_data = {}

        for line in po_lines:
            product = line.product_id
            if not product:
                continue
            key = product.id
            if key not in products_data:
                products_data[key] = {
                    'product': product,
                    'po_order_ids': set(),
                    'qty_commandee': 0.0,
                    'reception_ids': set(),
                    'qty_receptionnee': 0.0,
                }
            products_data[key]['qty_commandee'] += line.product_qty
            products_data[key]['po_order_ids'].add(line.order_id.name)

        for move in moves:
            product = move.product_id
            if not product:
                continue
            key = product.id
            if key not in products_data:
                products_data[key] = {
                    'product': product,
                    'po_order_ids': set(),
                    'qty_commandee': 0.0,
                    'reception_ids': set(),
                    'qty_receptionnee': 0.0,
                }
            qty_done = (
                sum(move.move_line_ids.mapped('quantity'))
                or move.product_uom_qty
            )
            products_data[key]['qty_receptionnee'] += qty_done
            if move.picking_id:
                products_data[key]['reception_ids'].add(move.picking_id.name)

        result = []
        for data in products_data.values():
            result.append({
                'ref': data['product'].default_code or '',
                'name': data['product'].name,
                'nb_commandes': len(data['po_order_ids']),
                'qty_commandee': data['qty_commandee'],
                'po_refs': ', '.join(sorted(data['po_order_ids'])),
                'nb_receptions': len(data['reception_ids']),
                'qty_receptionnee': data['qty_receptionnee'],
                'reception_refs': ', '.join(sorted(data['reception_ids'])),
            })

        result.sort(key=lambda x: (x['ref'].lower() if x['ref'] else x['name'].lower()))
        return result

    def action_print_report(self):
        self.ensure_one()
        self._get_report_data()
        return self.env.ref('custom_reports.action_report_achat_produit').report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            raise UserError("La bibliothèque openpyxl est requise.")

        data = self._get_report_data()

        wb = Workbook()
        ws = wb.active
        ws.title = "Cmdes & Réceptions Produits"

        BLUE  = "1A5276"
        WHITE = "FFFFFF"
        thin  = Side(style='thin', color="AAAAAA")
        brd   = Border(left=thin, right=thin, top=thin, bottom=thin)

        def hdr_font():
            return Font(name="Arial", bold=True, color=WHITE, size=10)

        def cell_font(bold=False):
            return Font(name="Arial", bold=bold, size=9)

        def fill(c):
            return PatternFill("solid", fgColor=c)

        def aln(h="left", v="center"):
            return Alignment(horizontal=h, vertical=v, wrap_text=True)

        # Ligne société
        ws.merge_cells("A1:H1")
        ws["A1"] = self.company_id.name
        ws["A1"].font = Font(name="Arial", bold=True, size=11)

        # Ligne titre
        ws.merge_cells("A2:H2")
        ws["A2"] = (
            f"COMMANDES & RÉCEPTIONS PAR PRODUIT — "
            f"Du {self.date_debut.strftime('%d/%m/%Y')} au {self.date_fin.strftime('%d/%m/%Y')}"
        )
        ws["A2"].font = Font(name="Arial", bold=True, color=WHITE, size=11)
        ws["A2"].fill = fill(BLUE)
        ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 18
        ws.append([])

        # En-têtes colonnes
        headers = [
            "Réf. Produit", "Désignation",
            "Nb Cmdes", "Qté Commandée", "Réf. Commandes",
            "Nb Réceptions", "Qté Réceptionnée", "Réf. Réceptions",
        ]
        ws.append(headers)
        hdr_row = ws.max_row
        for col in range(1, len(headers) + 1):
            c = ws.cell(row=hdr_row, column=col)
            c.font = hdr_font()
            c.fill = fill(BLUE)
            c.alignment = aln("center")
            c.border = brd
        ws.row_dimensions[hdr_row].height = 20

        # Données
        nb_cmdes_total = 0
        qty_cmd_total  = 0.0
        nb_rec_total   = 0
        qty_rec_total  = 0.0

        for i, row_data in enumerate(data):
            bg = "FFFFFF" if i % 2 == 0 else "EBF5FB"
            row = [
                row_data['ref'],
                row_data['name'],
                row_data['nb_commandes'],
                row_data['qty_commandee'],
                row_data['po_refs'],
                row_data['nb_receptions'],
                row_data['qty_receptionnee'],
                row_data['reception_refs'],
            ]
            ws.append(row)
            r = ws.max_row
            for col in range(1, 9):
                c = ws.cell(row=r, column=col)
                c.font = cell_font()
                c.fill = fill(bg)
                c.border = brd
                c.alignment = aln(
                    "right" if col in (3, 4, 6, 7) else
                    "center" if col == 1 else "left"
                )
            ws.cell(row=r, column=4).number_format = '#,##0.##'
            ws.cell(row=r, column=7).number_format = '#,##0.##'

            nb_cmdes_total += row_data['nb_commandes']
            qty_cmd_total  += row_data['qty_commandee']
            nb_rec_total   += row_data['nb_receptions']
            qty_rec_total  += row_data['qty_receptionnee']

        # Ligne total
        ws.append(["", "TOTAL", nb_cmdes_total, qty_cmd_total, "", nb_rec_total, qty_rec_total, ""])
        r = ws.max_row
        for col in range(1, 9):
            c = ws.cell(row=r, column=col)
            c.font = Font(name="Arial", bold=True, color=WHITE, size=10)
            c.fill = fill(BLUE)
            c.border = brd
            c.alignment = aln("right" if col in (3, 4, 6, 7) else "left")
        ws.cell(row=r, column=4).number_format = '#,##0.##'
        ws.cell(row=r, column=7).number_format = '#,##0.##'
        ws.row_dimensions[r].height = 18

        # Largeurs colonnes
        for col, w in enumerate([14, 36, 10, 14, 42, 12, 16, 42], 1):
            ws.column_dimensions[chr(64 + col)].width = w

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        xlsx_data = base64.b64encode(buf.read()).decode()

        fname = (
            f"Commandes_Receptions_Produits_"
            f"{self.date_debut.strftime('%d%m%Y')}_{self.date_fin.strftime('%d%m%Y')}.xlsx"
        )
        att = self.env['ir.attachment'].create({
            'name':      fname,
            'type':      'binary',
            'datas':     xlsx_data,
            'mimetype':  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id':    self.id,
        })
        return {
            'type':   'ir.actions.act_url',
            'url':    f'/web/content/{att.id}?download=true',
            'target': 'new',
        }
