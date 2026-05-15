# -*- coding: utf-8 -*-
import io
import base64
import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LimitCreditReportWizard(models.TransientModel):
    _name = 'limit.credit.report.wizard'
    _description = 'Rapport récapitulatif des crédits clients'

    partner_ids = fields.Many2many(
        'res.partner',
        string='Clients',
        domain=[('is_limit', '=', True)],
        help="Laisser vide pour inclure tous les clients avec une limite de crédit",
    )
    date_from = fields.Date(
        string='Date début',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Date fin',
        required=True,
        default=fields.Date.today,
    )
    report_type = fields.Selection([
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
    ], string='Format', default='pdf', required=True)

    def _get_report_data(self):
        domain = [('is_limit', '=', True)]
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))

        limits = self.env['limit.credit'].search(domain, order='partner_id')

        report_lines = []
        for limit in limits:
            op_domain = [
                ('limit_id', '=', limit.id),
                ('operation_date', '>=', datetime.combine(self.date_from, datetime.min.time())),
                ('operation_date', '<=', datetime.combine(self.date_to, datetime.max.time())),
            ]
            operations = self.env['limit.credit.operation'].search(op_domain, order='operation_date')

            report_lines.append({
                'partner_name': limit.partner_id.name or '',
                'amount_limit': limit.amount_limit,
                'amount_consumed': limit.amount_limit_consumed,
                'amount_solde': limit.amount_limit - limit.amount_limit_consumed,
                'operations': [{
                    'date': op.operation_date,
                    'name': op.name,
                    'amount': op.amount_operation,
                } for op in operations],
            })

        return report_lines

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError("La date de début doit être antérieure à la date de fin.")
        if self.report_type == 'pdf':
            return self._action_print_pdf()
        return self._action_print_excel()

    def _action_print_pdf(self):
        return self.env.ref('custom_food_credit.action_report_limit_credit').report_action(self)

    def _action_print_excel(self):
        try:
            import xlsxwriter
        except ImportError:
            raise UserError("La bibliothèque xlsxwriter est requise pour l'export Excel.")

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})

        # ── Formats ──────────────────────────────────────────────────────────
        title_fmt  = wb.add_format({'bold': True, 'font_size': 13, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#1a3a5c', 'font_color': 'white'})
        sub_fmt    = wb.add_format({'italic': True, 'align': 'center', 'font_color': '#555555'})
        header_fmt = wb.add_format({'bold': True, 'bg_color': '#1a3a5c', 'font_color': 'white', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True})
        client_fmt = wb.add_format({'bold': True, 'bg_color': '#dce6f1', 'border': 1, 'valign': 'top'})
        num_fmt    = wb.add_format({'num_format': '#,##0', 'border': 1, 'valign': 'top'})
        num_neg    = wb.add_format({'num_format': '#,##0', 'border': 1, 'font_color': '#cc0000', 'valign': 'top'})
        num_pos    = wb.add_format({'num_format': '#,##0', 'border': 1, 'font_color': '#007700', 'valign': 'top'})
        dt_fmt     = wb.add_format({'num_format': 'dd/mm/yyyy hh:mm', 'border': 1, 'valign': 'top'})
        cell_fmt   = wb.add_format({'border': 1, 'valign': 'top'})
        empty_fmt  = wb.add_format({'border': 1, 'italic': True, 'font_color': '#888888', 'valign': 'top'})

        ws = wb.add_worksheet('Récap Crédits')
        ws.set_zoom(90)
        ws.set_column('A:A', 28)
        ws.set_column('B:D', 18)
        ws.set_column('E:E', 35)
        ws.set_column('F:F', 18)
        ws.set_column('G:G', 16)

        # ── En-tête ───────────────────────────────────────────────────────────
        ws.set_row(0, 28)
        ws.merge_range('A1:G1', "RÉCAPITULATIF DES CRÉDITS CLIENTS", title_fmt)
        ws.set_row(1, 18)
        ws.merge_range(
            'A2:G2',
            f"Période : du {self.date_from.strftime('%d/%m/%Y')} au {self.date_to.strftime('%d/%m/%Y')}",
            sub_fmt,
        )

        # ── Colonnes ─────────────────────────────────────────────────────────
        ws.set_row(3, 30)
        cols = ['Client', 'Limite crédit (FCFA)', 'Consommé (FCFA)', 'Solde (FCFA)', 'Opération', 'Date', 'Montant (FCFA)']
        for c, h in enumerate(cols):
            ws.write(3, c, h, header_fmt)

        # ── Données ───────────────────────────────────────────────────────────
        row = 4
        for line in self._get_report_data():
            ops = line['operations']
            nb = max(len(ops), 1)

            # Colonnes client (fusionnées si plusieurs opérations)
            if nb > 1:
                ws.merge_range(row, 0, row + nb - 1, 0, line['partner_name'], client_fmt)
                ws.merge_range(row, 1, row + nb - 1, 1, line['amount_limit'], num_fmt)
                ws.merge_range(row, 2, row + nb - 1, 2, line['amount_consumed'], num_fmt)
                ws.merge_range(row, 3, row + nb - 1, 3, line['amount_solde'],
                               num_neg if line['amount_solde'] < 0 else num_fmt)
            else:
                ws.write(row, 0, line['partner_name'], client_fmt)
                ws.write(row, 1, line['amount_limit'], num_fmt)
                ws.write(row, 2, line['amount_consumed'], num_fmt)
                ws.write(row, 3, line['amount_solde'],
                         num_neg if line['amount_solde'] < 0 else num_fmt)

            if ops:
                for op in ops:
                    ws.write(row, 4, op['name'], cell_fmt)
                    ws.write_datetime(row, 5, op['date'], dt_fmt)
                    ws.write(row, 6, op['amount'], num_neg if op['amount'] < 0 else num_pos)
                    row += 1
            else:
                ws.write(row, 4, 'Aucune opération sur la période', empty_fmt)
                ws.write(row, 5, '', cell_fmt)
                ws.write(row, 6, '', cell_fmt)
                row += 1

        wb.close()
        output.seek(0)

        filename = f"recap_credits_{self.date_from}_{self.date_to}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class ReportLimitCredit(models.AbstractModel):
    _name = 'report.custom_food_credit.report_limit_credit_template'
    _description = 'Rapport PDF crédits clients'

    def _get_report_values(self, docids, data=None):
        wizard = self.env['limit.credit.report.wizard'].browse(docids)
        return {
            'docs': wizard,
            'date_from': wizard.date_from,
            'date_to': wizard.date_to,
            'report_lines': wizard._get_report_data(),
        }
