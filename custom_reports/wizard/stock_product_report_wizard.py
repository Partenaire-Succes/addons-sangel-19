# -*- coding: utf-8 -*-
import io
import xlsxwriter
import base64

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockMagasinReportWizard(models.TransientModel):
    _name = 'stock.magasin.report.wizard'
    _description = 'Wizard Rapport Stock Magasin'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Société',
        required=True,
        default=lambda self: self.env.company,
    )

    def action_generate_report(self):
        self.ensure_one()
        company = self.company_id

        # ── 1. Récupérer les produits actifs de la société ──────────────────
        type_x3 = self.env['product.type.x3'].search([('name', '=', 'TS')], limit=1)

        # ── Filtres produits ─────────────────────────────────────────────────
        products = self.env['product.template'].with_company(company).search([
            ('active', '=', True),
            ('type', '=', 'consu'),
            ('allowed_company_ids', 'in', company.id),
            *([('prod_type_x3_id', '=', type_x3.id)] if type_x3 else []),
        ])
        products = products.filtered(lambda p: p.current_company_status_id)

        if not products:
            raise UserError(_("Aucun article trouvé pour la société %s.") % company.name)

        # ── 2. Stock disponible par produit (filtré par société) ─────────────
        # On récupère les emplacements internes de la société
        warehouses = self.env['stock.warehouse'].search([('company_id', '=', company.id)])
        location_ids = warehouses.mapped('lot_stock_id').ids

        # qty_available via stock.quant groupé par product_tmpl_id
        quant_data = {}
        if location_ids:
            quants = self.env['stock.quant'].read_group(
                domain=[
                    ('location_id', 'in', location_ids),
                    ('product_id.active', '=', True),
                ],
                fields=['product_tmpl_id', 'quantity:sum'],
                groupby=['product_tmpl_id'],
            )
            quant_data = {q['product_tmpl_id'][0]: q['quantity'] for q in quants}

        # ── 3. Stock max via les règles de réapprovisionnement ───────────────
        orderpoint_data = {}
        orderpoints = self.env['stock.warehouse.orderpoint'].search([
            ('company_id', '=', company.id),
        ])
        for op in orderpoints:
            tmpl_id = op.product_id.product_tmpl_id.id
            qty_max = op.product_max_qty or 0.0
            # On prend le max si plusieurs règles pour le même produit
            if tmpl_id not in orderpoint_data or qty_max > orderpoint_data[tmpl_id]:
                orderpoint_data[tmpl_id] = qty_max

        # ── 4. Générer le fichier Excel ──────────────────────────────────────
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Stock Magasin')

        # ── Formats ──────────────────────────────────────────────────────────
        fmt_header = workbook.add_format({
            'bold': True,
            'font_name': 'Arial',
            'font_size': 10,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })
        fmt_row_light = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'border': 1,
            'valign': 'vcenter',
        })
        fmt_row_white = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'border': 1,
            'valign': 'vcenter',
        })
        fmt_number_light = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'border': 1,
            'num_format': '#,##0.00',
            'valign': 'vcenter',
        })
        fmt_number_white = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'border': 1,
            'num_format': '#,##0.00',
            'valign': 'vcenter',
        })

        # ── En-têtes ─────────────────────────────────────────────────────────
        headers = [
            ('article',         12),
            ('designation',     40),
            ('statut_article',  14),
            ('unite_vente',     12),
            ('stock_max',       12),
            ('STOCK MAGASIN',   16),
        ]
        for col, (label, width) in enumerate(headers):
            sheet.write(0, col, label, fmt_header)
            sheet.set_column(col, col, width)
        sheet.set_row(0, 18)

        # ── Données ──────────────────────────────────────────────────────────
        for row_idx, product in enumerate(products, start=1):
            fmt_txt = fmt_row_light if row_idx % 2 == 0 else fmt_row_white
            fmt_num = fmt_number_light if row_idx % 2 == 0 else fmt_number_white

            code        = product.default_code or ''
            designation = product.name or ''
            statut      = product.current_company_status_id.code if product.current_company_status_id else ''
            uom         = product.uom_id.name if product.uom_id else ''
            stock_max   = orderpoint_data.get(product.id, 0.0)
            qty_avail   = quant_data.get(product.id, 0.0)

            sheet.write(row_idx, 0, code,        fmt_txt)
            sheet.write(row_idx, 1, designation, fmt_txt)
            sheet.write(row_idx, 2, statut,      fmt_txt)
            sheet.write(row_idx, 3, uom,         fmt_txt)
            sheet.write(row_idx, 4, stock_max,   fmt_num)
            sheet.write(row_idx, 5, qty_avail,   fmt_num)

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())

        # ── 5. Créer la pièce jointe et déclencher le téléchargement ─────────
        attachment = self.env['ir.attachment'].create({
            'name': f'Stock_Magasin_{company.name}.xlsx',
            'type': 'binary',
            'datas': file_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }