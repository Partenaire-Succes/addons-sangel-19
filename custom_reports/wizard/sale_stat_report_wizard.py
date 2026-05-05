# -*- coding: utf-8 -*-
import io
import base64
from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleStatReportWizard(models.TransientModel):
    _name = 'sale.stat.report.wizard'
    _description = 'Assistant Statistiques de Ventes'

    date_start_period1 = fields.Date(string='Début Période 1')
    date_end_period1 = fields.Date(string='Fin Période 1')
    date_start_period2 = fields.Date(string='Début Période 2')
    date_end_period2 = fields.Date(string='Fin Période 2',)

    partner_ids = fields.Many2many(
        'res.partner',
        string='Clients',
        domain=[('customer_rank', '>', 0)]
    )

    category_ids = fields.Many2many(
        'res.partner.category',
        string='Catégories clients',
        help='Laissez vide pour toutes les catégories'
    )


    company_id = fields.Many2one(
        'res.company',
        string='Société',
        default=lambda self: self.env.company
    )

    report_mode = fields.Selection([
        ('single', 'Une période'),
        ('comparison', 'Comparaison deux périodes'),
    ], string='Mode', default='comparison', required=True)

    @api.constrains('date_start_period1', 'date_end_period1', 'date_start_period2', 'date_end_period2')
    def _check_dates(self):
        for record in self:
            if record.date_start_period1 and record.date_end_period1:
                if record.date_start_period1 > record.date_end_period1:
                    raise UserError("La date de début de la période 1 doit être avant la date de fin.")
            if record.report_mode == 'comparison':
                if record.date_start_period2 and record.date_end_period2:
                    if record.date_start_period2 > record.date_end_period2:
                        raise UserError("La date de début de la période 2 doit être avant la date de fin.")

    def get_sale_data_by_category(self):
        """Retourne un dictionnaire des ventes groupées par catégorie client."""
        self.ensure_one()

        PosOrder = self.env['pos.order']

        # Domaine de base
        domain_base = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('company_id', '=', self.company_id.id),
        ]

        if self.partner_ids:
            domain_base.append(('partner_id', 'in', self.partner_ids.ids))

        # Domaine période 1
        domain_p1 = domain_base + [
            ('date_order', '>=', fields.Datetime.to_datetime(self.date_start_period1)),
            ('date_order', '<=',
             fields.Datetime.to_datetime(self.date_end_period1).replace(hour=23, minute=59, second=59)),
        ]

        orders_p1 = PosOrder.search(domain_p1)

        orders_p2 = PosOrder
        if self.report_mode == 'comparison':
            domain_p2 = domain_base + [
                ('date_order', '>=', fields.Datetime.to_datetime(self.date_start_period2)),
                ('date_order', '<=',
                 fields.Datetime.to_datetime(self.date_end_period2).replace(hour=23, minute=59, second=59)),
            ]
            orders_p2 = PosOrder.search(domain_p2)

        # Structure de données par catégorie
        categories_data = {}

        def add_order(order, period):
            partner = order.partner_id
            categories = partner.category_id

            # Si filtrage par catégories activé
            if self.category_ids:
                categories = categories.filtered(lambda c: c.id in self.category_ids.ids)

            # Si pas de catégorie, créer "Sans Catégorie"
            if not categories:
                cat_key = 'Sans Catégorie'
                cat_id = 0
            else:
                # Pour chaque catégorie du client
                for categ in categories:
                    process_category(categ, partner, order, period)
                return

            # Traitement pour "Sans Catégorie"
            if cat_key not in categories_data:
                categories_data[cat_key] = {
                    'category_id': cat_id,
                    'category_name': cat_key,
                    'clients': {},
                    'total_p1_qty': 0,
                    'total_p1_ca': 0.0,
                    'total_p1_margin': 0.0,
                    'total_p2_qty': 0,
                    'total_p2_ca': 0.0,
                    'total_p2_margin': 0.0,
                }

            add_partner_data(categories_data[cat_key], partner, order, period)

        def process_category(categ, partner, order, period):
            cat_key = categ.name

            if cat_key not in categories_data:
                categories_data[cat_key] = {
                    'category_id': categ.id,
                    'category_name': cat_key,
                    'clients': {},
                    'total_p1_qty': 0,
                    'total_p1_ca': 0.0,
                    'total_p1_margin': 0.0,
                    'total_p2_qty': 0,
                    'total_p2_ca': 0.0,
                    'total_p2_margin': 0.0,
                }

            add_partner_data(categories_data[cat_key], partner, order, period)

        def add_partner_data(cat_data, partner, order, period):
            if partner.id not in cat_data['clients']:
                cat_data['clients'][partner.id] = {
                    'partner_name': partner.name or '',
                    'partner_ref': partner.ref or '',
                    'customer_id': partner.customer_id or '',
                    'qty_p1': 0,
                    'ca_p1': 0.0,
                    'margin_p1': 0.0,
                    'margin_pct_p1': 0.0,
                    'qty_p2': 0,
                    'ca_p2': 0.0,
                    'margin_p2': 0.0,
                    'margin_pct_p2': 0.0,
                    'prog_qty': 0,
                    'prog_ca': 0.0,
                    'prog_margin': 0.0,
                    'prog_ca_pct': 0.0,
                    'prog_margin_pct': 0.0,
                }

            data = cat_data['clients'][partner.id]
            amount_ht = (order.amount_total or 0.0) - (order.amount_tax or 0.0)
            margin = order.margin or 0.0

            if period == 1:
                data['qty_p1'] += 1
                data['ca_p1'] += amount_ht
                data['margin_p1'] += margin

                cat_data['total_p1_qty'] += 1
                cat_data['total_p1_ca'] += amount_ht
                cat_data['total_p1_margin'] += margin
            else:
                data['qty_p2'] += 1
                data['ca_p2'] += amount_ht
                data['margin_p2'] += margin

                cat_data['total_p2_qty'] += 1
                cat_data['total_p2_ca'] += amount_ht
                cat_data['total_p2_margin'] += margin

        # Traiter toutes les commandes
        for o in orders_p1:
            add_order(o, 1)
        for o in orders_p2:
            add_order(o, 2)

        # Calcul des marges % et progressions
        for cat_key, cat_data in categories_data.items():
            for partner_id, vals in cat_data['clients'].items():
                if vals['ca_p1'] > 0:
                    vals['margin_pct_p1'] = (vals['margin_p1'] / vals['ca_p1']) * 100

                if self.report_mode == 'comparison':
                    if vals['ca_p2'] > 0:
                        vals['margin_pct_p2'] = (vals['margin_p2'] / vals['ca_p2']) * 100
                    vals['prog_qty'] = vals['qty_p2'] - vals['qty_p1']
                    vals['prog_ca'] = vals['ca_p2'] - vals['ca_p1']
                    vals['prog_margin'] = vals['margin_p2'] - vals['margin_p1']
                    if vals['ca_p1'] > 0:
                        vals['prog_ca_pct'] = (vals['prog_ca'] / vals['ca_p1']) * 100
                    else:
                        vals['prog_ca_pct'] = 100.0 if vals['ca_p2'] > 0 else 0.0
                    if vals['margin_p1'] > 0:
                        vals['prog_margin_pct'] = (vals['prog_margin'] / vals['margin_p1']) * 100
                    else:
                        vals['prog_margin_pct'] = 100.0 if vals['margin_p2'] > 0 else 0.0

            if cat_data['total_p1_ca'] > 0:
                cat_data['total_p1_margin_pct'] = (cat_data['total_p1_margin'] / cat_data['total_p1_ca']) * 100
            else:
                cat_data['total_p1_margin_pct'] = 0.0

            if self.report_mode == 'comparison':
                if cat_data['total_p2_ca'] > 0:
                    cat_data['total_p2_margin_pct'] = (cat_data['total_p2_margin'] / cat_data['total_p2_ca']) * 100
                else:
                    cat_data['total_p2_margin_pct'] = 0.0
                cat_data['total_prog_qty'] = cat_data['total_p2_qty'] - cat_data['total_p1_qty']
                cat_data['total_prog_ca'] = cat_data['total_p2_ca'] - cat_data['total_p1_ca']
                cat_data['total_prog_margin'] = cat_data['total_p2_margin'] - cat_data['total_p1_margin']
                if cat_data['total_p1_ca'] > 0:
                    cat_data['total_prog_ca_pct'] = (cat_data['total_prog_ca'] / cat_data['total_p1_ca']) * 100
                else:
                    cat_data['total_prog_ca_pct'] = 100.0 if cat_data['total_p2_ca'] > 0 else 0.0

        # Trier les catégories par nom
        return dict(sorted(categories_data.items()))

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('custom_reports.action_report_sale_statistics').report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            raise UserError("La bibliothèque openpyxl est requise.")

        categories_data = self.get_sale_data_by_category()
        if not categories_data:
            raise UserError("Aucune donnée trouvée pour la période sélectionnée.")

        wb = Workbook(); ws = wb.active; ws.title = "Stats Ventes"
        BLUE = "1A5276"; LBLUE = "D6EAF8"; WHITE = "FFFFFF"
        thin = Side(style='thin', color="AAAAAA")
        brd  = Border(left=thin, right=thin, top=thin, bottom=thin)
        def fill(h): return PatternFill("solid", fgColor=h)
        def aln(h="left"): return Alignment(horizontal=h, vertical="center")

        is_comparison = self.report_mode == 'comparison'
        p1_label = f"{self.date_start_period1.strftime('%d/%m/%Y')} → {self.date_end_period1.strftime('%d/%m/%Y')}" if self.date_start_period1 else "Période 1"

        last_col = 12 if is_comparison else 6
        last_col_letter = chr(64 + last_col)
        merge_range = f"A1:{last_col_letter}1"

        ws.merge_cells(merge_range)
        ws["A1"] = self.company_id.name
        ws["A1"].font = Font(name="Arial", bold=True, size=11)

        ws.merge_cells(f"A2:{last_col_letter}2")
        if is_comparison:
            p2_label = f"{self.date_start_period2.strftime('%d/%m/%Y')} → {self.date_end_period2.strftime('%d/%m/%Y')}" if self.date_start_period2 else "Période 2"
            ws["A2"] = f"STATISTIQUES VENTES — P1: {p1_label} | P2: {p2_label}"
        else:
            ws["A2"] = f"STATISTIQUES VENTES — {p1_label}"
        ws["A2"].font = Font(name="Arial", bold=True, color=WHITE, size=11)
        ws["A2"].fill = fill(BLUE); ws["A2"].alignment = aln("center")
        ws.row_dimensions[2].height = 18; ws.append([])

        if is_comparison:
            headers = ["Catégorie", "Client", "Qté P1", "CA HT P1", "Marge P1", "% Marge P1",
                       "Qté P2", "CA HT P2", "Marge P2", "% Marge P2", "Prog CA", "% Prog CA"]
            money_cols_data = (4, 5, 8, 9, 11)
            money_cols_sub = (4, 5, 8, 9, 11)
        else:
            headers = ["Catégorie", "Client", "Qté", "CA HT", "Marge", "% Marge"]
            money_cols_data = (4, 5)
            money_cols_sub = (4, 5)

        ws.append(headers)
        hrow = ws.max_row
        for col in range(1, last_col + 1):
            c = ws.cell(row=hrow, column=col)
            c.font = Font(name="Arial", bold=True, color=WHITE, size=10)
            c.fill = fill(BLUE); c.alignment = aln("center"); c.border = brd

        for cat_key, cat_data in categories_data.items():
            for client in cat_data['clients'].values():
                if is_comparison:
                    row_data = [
                        cat_data['category_name'], client['partner_name'],
                        client['qty_p1'], client['ca_p1'], client['margin_p1'], round(client['margin_pct_p1'], 2),
                        client['qty_p2'], client['ca_p2'], client['margin_p2'], round(client['margin_pct_p2'], 2),
                        client['prog_ca'], round(client['prog_ca_pct'], 2),
                    ]
                else:
                    row_data = [
                        cat_data['category_name'], client['partner_name'],
                        client['qty_p1'], client['ca_p1'], client['margin_p1'], round(client['margin_pct_p1'], 2),
                    ]
                ws.append(row_data)
                r = ws.max_row
                for col in range(1, last_col + 1):
                    c = ws.cell(row=r, column=col)
                    c.font = Font(name="Arial", size=9); c.border = brd
                    c.alignment = aln("right" if col >= 3 else "left")
                for col in money_cols_data:
                    ws.cell(row=r, column=col).number_format = '#,##0.00'

            if is_comparison:
                sub_row = [
                    "Sous-total " + cat_data['category_name'], "",
                    cat_data['total_p1_qty'], cat_data['total_p1_ca'], cat_data['total_p1_margin'], round(cat_data.get('total_p1_margin_pct', 0.0), 2),
                    cat_data['total_p2_qty'], cat_data['total_p2_ca'], cat_data['total_p2_margin'], round(cat_data.get('total_p2_margin_pct', 0.0), 2),
                    cat_data.get('total_prog_ca', 0.0), round(cat_data.get('total_prog_ca_pct', 0.0), 2),
                ]
            else:
                sub_row = [
                    "Sous-total " + cat_data['category_name'], "",
                    cat_data['total_p1_qty'], cat_data['total_p1_ca'], cat_data['total_p1_margin'], round(cat_data.get('total_p1_margin_pct', 0.0), 2),
                ]
            ws.append(sub_row)
            r = ws.max_row
            for col in range(1, last_col + 1):
                c = ws.cell(row=r, column=col)
                c.font = Font(name="Arial", bold=True, size=9)
                c.fill = fill(LBLUE); c.border = brd
                c.alignment = aln("right" if col >= 3 else "left")
            for col in money_cols_sub:
                ws.cell(row=r, column=col).number_format = '#,##0.00'

        if is_comparison:
            col_widths = [22, 25, 8, 14, 14, 10, 8, 14, 14, 10, 14, 10]
        else:
            col_widths = [22, 25, 8, 14, 14, 10]
        for col, width in enumerate(col_widths, 1):
            ws.column_dimensions[chr(64 + col)].width = width

        buffer = io.BytesIO(); wb.save(buffer); buffer.seek(0)
        xlsx_data = base64.b64encode(buffer.read()).decode()
        filename = "Stats_Ventes.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename, 'type': 'binary', 'datas': xlsx_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name, 'res_id': self.id,
        })
        return {'type': 'ir.actions.act_url', 'url': f'/web/content/{attachment.id}?download=true', 'target': 'new'}