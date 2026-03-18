# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta


class CfaoDashboardReport(models.AbstractModel):
    _name = 'report.cfao_dashboard_report.cfao_dashboard_main'
    _description = 'CFAO Tableau de Bord Quotidien'

    # ──────────────────────────────────────────────────────────────
    # PÉRIODES
    # ──────────────────────────────────────────────────────────────

    def _get_periods(self, analysis_date):
        day_from   = datetime.combine(analysis_date, datetime.min.time())
        day_to     = datetime.combine(analysis_date, datetime.max.time())
        monday     = analysis_date - timedelta(days=analysis_date.weekday())
        week_from  = datetime.combine(monday, datetime.min.time())
        week_to    = datetime.combine(analysis_date, datetime.max.time())
        month_from = datetime.combine(analysis_date.replace(day=1), datetime.min.time())
        month_to   = datetime.combine(analysis_date, datetime.max.time())
        year_from  = datetime.combine(analysis_date.replace(month=1, day=1), datetime.min.time())
        year_to    = datetime.combine(analysis_date, datetime.max.time())

        prev     = analysis_date - relativedelta(years=1)
        prev_mon = prev - timedelta(days=prev.weekday())

        return {
            'jour': {
                'from': day_from, 'to': day_to,
                'n1_from': datetime.combine(prev, datetime.min.time()),
                'n1_to':   datetime.combine(prev, datetime.max.time()),
                'label': 'DONNEES DU JOUR',
                'meta':  analysis_date.strftime('%d/%m/%Y'),
                'color': '#D97706',
            },
            'semaine': {
                'from': week_from, 'to': week_to,
                'n1_from': datetime.combine(prev_mon, datetime.min.time()),
                'n1_to':   datetime.combine(prev, datetime.max.time()),
                'label': 'WTD - CUMUL SEMAINE',
                'meta':  '{} au {}'.format(
                    monday.strftime('%d/%m/%Y'),
                    analysis_date.strftime('%d/%m/%Y')),
                'color': '#2563EB',
            },
            'mois': {
                'from': month_from, 'to': month_to,
                'n1_from': datetime.combine(prev.replace(day=1), datetime.min.time()),
                'n1_to':   datetime.combine(prev, datetime.max.time()),
                'label': 'MTD - CUMUL MOIS',
                'meta':  '{} au {}'.format(
                    analysis_date.replace(day=1).strftime('%d/%m/%Y'),
                    analysis_date.strftime('%d/%m/%Y')),
                'color': '#059669',
            },
            'annee': {
                'from': year_from, 'to': year_to,
                'n1_from': datetime.combine(prev.replace(month=1, day=1), datetime.min.time()),
                'n1_to':   datetime.combine(prev, datetime.max.time()),
                'label': 'YTD - CUMUL ANNEE',
                'meta':  '{} au {}'.format(
                    analysis_date.replace(month=1, day=1).strftime('%d/%m/%Y'),
                    analysis_date.strftime('%d/%m/%Y')),
                'color': '#7C3AED',
            },
        }

    # ──────────────────────────────────────────────────────────────
    # REQUÊTES — filtrées par categ_id EXACT
    # ──────────────────────────────────────────────────────────────

    def _get_pos_lines(self, company_id, categ_id, date_from, date_to):
        return self.env['pos.order.line'].sudo().search([
            ('order_id.company_id', '=', company_id),
            ('order_id.state', 'in', ['paid', 'done', 'invoiced']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to),
            ('product_id.categ_id', '=', categ_id),
        ])

    def _get_sale_lines(self, company_id, categ_id, date_from, date_to):
        # NOTE : sale.order.line utilise tax_ids (Many2many) en Odoo 17+
        return self.env['sale.order.line'].sudo().search([
            ('order_id.company_id', '=', company_id),
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to),
            ('product_id.categ_id', '=', categ_id),
        ])

    def _get_stock_received(self, company_id, categ_id, date_from, date_to):
        moves = self.env['stock.move'].sudo().search([
            ('company_id', '=', company_id),
            ('product_id.categ_id', '=', categ_id),
            ('state', '=', 'done'),
            ('picking_type_id.code', '=', 'incoming'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ])
        qty   = sum(m.product_uom_qty for m in moves)
        value = sum(m.product_uom_qty * m.product_id.standard_price for m in moves)
        return qty, value

    def _get_stock_on_hand_value(self, company_id, categ_id):
        quants = self.env['stock.quant'].sudo().search([
            ('company_id', '=', company_id),
            ('product_id.categ_id', '=', categ_id),
            ('location_id.usage', '=', 'internal'),
        ])
        return sum(q.quantity * q.product_id.standard_price for q in quants)

    # ──────────────────────────────────────────────────────────────
    # AGRÉGATION
    # ──────────────────────────────────────────────────────────────

    def _aggregate(self, pos_lines, sale_lines):
        ca_ttc = ca_ht = marge = 0.0
        ca_promo = ca_hspromo = ca_import = ca_local = 0.0
        marge_promo = marge_import = 0.0

        for line in pos_lines:
            ht   = line.price_subtotal
            ttc  = line.price_subtotal_incl
            cost = line.product_id.standard_price * (line.qty or 0)
            mg   = ht - cost
            is_promo = bool(line.discount and line.discount > 0)
            is_imp   = getattr(line.product_id.product_tmpl_id, 'is_imported', False)

            ca_ttc += ttc
            ca_ht  += ht
            marge  += mg

            if is_promo:
                ca_promo    += ht
                marge_promo += mg
            else:
                ca_hspromo  += ht

            if is_imp:
                ca_import    += ht
                marge_import += mg
            else:
                ca_local += ht

        for line in sale_lines:
            ht   = line.price_subtotal
            cost = line.product_id.standard_price * (line.product_uom_qty or 0)
            mg   = ht - cost
            # tax_ids est le champ correct sur sale.order.line (Odoo 17+)
            taxes = line.tax_ids
            if taxes:
                tr  = taxes.compute_all(
                    line.price_unit, line.order_id.currency_id,
                    line.product_uom_qty, line.product_id)
                ttc = tr['total_included']
            else:
                ttc = ht

            is_promo = bool(line.discount and line.discount > 0)
            is_imp   = getattr(line.product_id.product_tmpl_id.categ_id, 'is_imported', False)

            ca_ttc += ttc
            ca_ht  += ht
            marge  += mg

            if is_promo:
                ca_promo    += ht
                marge_promo += mg
            else:
                ca_hspromo  += ht

            if is_imp:
                ca_import    += ht
                marge_import += mg
            else:
                ca_local += ht

        return {
            'ca_ttc': ca_ttc, 'ca_ht': ca_ht, 'marge': marge,
            'ca_promo': ca_promo, 'ca_hspromo': ca_hspromo,
            'ca_import': ca_import, 'ca_local': ca_local,
            'marge_promo': marge_promo, 'marge_import': marge_import,
        }

    # ──────────────────────────────────────────────────────────────
    # KPIs
    # ──────────────────────────────────────────────────────────────

    def _compute_kpis(self, cur, prev, tickets, tickets_n1,
                      stk_qty_r, stk_val_r, stk_oh, nb_days):

        def _pct(a, b):
            return round((a - b) / abs(b) * 100, 2) if b else 0.0

        def _rate(a, b):
            return round(a / b * 100, 2) if b else 0.0

        panier    = round(cur['ca_ttc'] / tickets,    2) if tickets    else 0.0
        panier_n1 = round(prev['ca_ttc'] / tickets_n1, 2) if tickets_n1 else 0.0
        ht_day    = cur['ca_ht'] / nb_days if cur['ca_ht'] else 0
        couv      = round(stk_oh / ht_day, 2) if ht_day else 0.0

        return {
            'ca_ttc':           round(cur['ca_ttc'] / 1000, 2),
            'ca_ht':            round(cur['ca_ht']  / 1000, 2),
            'pct_n1':           _pct(cur['ca_ttc'], prev['ca_ttc']),
            'pct_promo':        _rate(cur['ca_promo'],  cur['ca_ht']),
            'pct_import':       _rate(cur['ca_import'], cur['ca_ht']),
            'pct_local':        _rate(cur['ca_local'],  cur['ca_ht']),
            'ecart_budget':     0.0,
            'pct_budget':       0.0,
            'debits':           tickets,
            'pct_prog':         _pct(tickets, tickets_n1),
            'marge':            round(cur['marge'] / 1000, 2),
            'pct_marge':        _rate(cur['marge'],                       cur['ca_ht']),
            'pct_marge_import': _rate(cur['marge_import'],                cur['ca_import']),
            'pct_marge_local':  _rate(cur['marge'] - cur['marge_import'], cur['ca_local']),
            'pct_hs_promo':     _rate(cur['ca_hspromo'],                  cur['ca_ht']),
            'pct_promo_marge':  _rate(cur['marge_promo'],                 cur['ca_ht']),
            'pct_dem':          _pct(cur['marge'], prev['marge']),
            'panier_moyen':     panier,
            'pct_panier_n1':    _pct(panier, panier_n1),
            'stock_qty':        round(stk_qty_r / 1000, 2),
            'stock_valo':       round(stk_val_r / 1000, 2),
            'couverture':       couv,
        }

    # ──────────────────────────────────────────────────────────────
    # TOTAL GÉNÉRAL
    # ──────────────────────────────────────────────────────────────

    def _compute_total_kpis(self, raw_list):
        def _s(k):
            return sum(r.get(k, 0.0) for r in raw_list)

        def _pct(a, b):
            return round((a - b) / abs(b) * 100, 2) if b else 0.0

        def _rate(a, b):
            return round(a / b * 100, 2) if b else 0.0

        ca_ttc    = _s('ca_ttc')
        ca_ht     = _s('ca_ht')
        ca_ttc_n1 = _s('ca_ttc_n1')
        marge     = _s('marge')
        marge_n1  = _s('marge_n1')
        ca_promo  = _s('ca_promo')
        ca_import = _s('ca_import')
        ca_local  = _s('ca_local')
        ca_hspromo= _s('ca_hspromo')
        mg_import = _s('marge_import')
        mg_promo  = _s('marge_promo')
        tickets   = int(_s('tickets'))
        tkt_n1    = int(_s('tickets_n1'))
        stk_qty   = _s('stk_qty')
        stk_val   = _s('stk_val')
        stk_oh    = _s('stk_oh')
        nb_days   = _s('nb_days') / max(len(raw_list), 1)

        panier    = round(ca_ttc / tickets, 2)    if tickets else 0.0
        panier_n1 = round(ca_ttc_n1 / tkt_n1, 2) if tkt_n1  else 0.0
        ht_day    = ca_ht / nb_days if ca_ht and nb_days else 0
        couv      = round(stk_oh / ht_day, 2) if ht_day else 0.0

        return {
            'ca_ttc':           round(ca_ttc / 1000, 2),
            'ca_ht':            round(ca_ht  / 1000, 2),
            'pct_n1':           _pct(ca_ttc, ca_ttc_n1),
            'pct_promo':        _rate(ca_promo,  ca_ht),
            'pct_import':       _rate(ca_import, ca_ht),
            'pct_local':        _rate(ca_local,  ca_ht),
            'ecart_budget':     0.0,
            'pct_budget':       0.0,
            'debits':           tickets,
            'pct_prog':         _pct(tickets, tkt_n1),
            'marge':            round(marge / 1000, 2),
            'pct_marge':        _rate(marge,             ca_ht),
            'pct_marge_import': _rate(mg_import,         ca_import),
            'pct_marge_local':  _rate(marge - mg_import, ca_local),
            'pct_hs_promo':     _rate(ca_hspromo,        ca_ht),
            'pct_promo_marge':  _rate(mg_promo,          ca_ht),
            'pct_dem':          _pct(marge, marge_n1),
            'panier_moyen':     panier,
            'pct_panier_n1':    _pct(panier, panier_n1),
            'stock_qty':        round(stk_qty / 1000, 2),
            'stock_valo':       round(stk_val / 1000, 2),
            'couverture':       couv,
        }

    # ──────────────────────────────────────────────────────────────
    # CONSTRUCTION D'UNE PÉRIODE
    # ──────────────────────────────────────────────────────────────

    def _build_period_data(self, company, analysis_date,
                           date_from, date_to, date_from_n1, date_to_n1):
        nb_days = max((date_to.date() - date_from.date()).days + 1, 1)

        pos_categs  = self.env['pos.order.line'].sudo().search([
            ('order_id.company_id', '=', company.id),
            ('order_id.state', 'in', ['paid', 'done', 'invoiced']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to),
        ]).mapped('product_id.categ_id')

        sale_categs = self.env['sale.order.line'].sudo().search([
            ('order_id.company_id', '=', company.id),
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to),
        ]).mapped('product_id.categ_id')

        categories = (pos_categs | sale_categs).sorted(
            key=lambda c: c.complete_name or c.name)

        rows     = []
        raw_list = []

        for categ in categories:
            pl    = self._get_pos_lines(company.id,  categ.id, date_from,    date_to)
            sl    = self._get_sale_lines(company.id, categ.id, date_from,    date_to)
            pl_n1 = self._get_pos_lines(company.id,  categ.id, date_from_n1, date_to_n1)
            sl_n1 = self._get_sale_lines(company.id, categ.id, date_from_n1, date_to_n1)

            cur  = self._aggregate(pl,    sl)
            prev = self._aggregate(pl_n1, sl_n1)

            tickets   = len(pl.mapped('order_id')) + len(sl.mapped('order_id'))
            tickets_n1= len(pl_n1.mapped('order_id')) + len(sl_n1.mapped('order_id'))

            stk_qty_r, stk_val_r = self._get_stock_received(
                company.id, categ.id, date_from, date_to)
            stk_oh = self._get_stock_on_hand_value(company.id, categ.id)

            kpis = self._compute_kpis(
                cur, prev, tickets, tickets_n1,
                stk_qty_r, stk_val_r, stk_oh, nb_days)

            rows.append({
                'type':     'categ',
                'name':     categ.name,
                'fullname': categ.complete_name or categ.name,
                'kpis':     kpis,
            })

            raw_list.append({
                'ca_ttc':    cur['ca_ttc'],
                'ca_ht':     cur['ca_ht'],
                'ca_ttc_n1': prev['ca_ttc'],
                'marge':     cur['marge'],
                'marge_n1':  prev['marge'],
                'ca_promo':  cur['ca_promo'],
                'ca_import': cur['ca_import'],
                'ca_local':  cur['ca_local'],
                'ca_hspromo':cur['ca_hspromo'],
                'marge_import': cur['marge_import'],
                'marge_promo':  cur['marge_promo'],
                'tickets':   tickets,
                'tickets_n1':tickets_n1,
                'stk_qty':   stk_qty_r,
                'stk_val':   stk_val_r,
                'stk_oh':    stk_oh,
                'nb_days':   nb_days,
            })

        if rows:
            rows.append({
                'type': 'total',
                'name': 'TOTAL GENERAL',
                'kpis': self._compute_total_kpis(raw_list),
            })

        return rows

    # ──────────────────────────────────────────────────────────────
    # POINT D'ENTRÉE
    # ──────────────────────────────────────────────────────────────

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data:
            raise UserError(_("Aucune donnée transmise au rapport."))

        analysis_date = fields.Date.from_string(data.get('analysis_date')) \
            if data.get('analysis_date') else date.today()

        company_ids = data.get('company_ids') or [self.env.company.id]
        companies   = self.env['res.company'].sudo().browse(company_ids)
        periods     = self._get_periods(analysis_date)

        docs = []
        for company in companies:
            # Construire les 4 tableaux avec label/meta/color inclus
            period_blocks = []
            for key in ['jour', 'semaine', 'mois', 'annee']:
                p = periods[key]
                rows = self._build_period_data(
                    company, analysis_date,
                    p['from'], p['to'],
                    p['n1_from'], p['n1_to'],
                )
                period_blocks.append({
                    'key':   key,
                    'label': p['label'],
                    'meta':  p['meta'],
                    'color': p['color'],
                    'rows':  rows,
                })

            docs.append({
                'company':       company,
                'analysis_date': analysis_date,
                'period_blocks': period_blocks,
            })

        return {
            'doc_ids':   docids,
            'doc_model': 'cfao.dashboard.wizard',
            'docs':      docs,
        }
