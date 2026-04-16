# -*- coding: utf-8 -*-
import logging
from datetime import date
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class RecapCaissesWizard(models.TransientModel):
    _name = 'recap.caisses.wizard'
    _description = 'Récapitulatif des Caisses'

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
    config_ids = fields.Many2many(
        'pos.config',
        string='Poste(s)',
        domain="[('company_id', '=', company_id)]",
        help="Laisser vide pour inclure tous les postes de la société",
    )
    caissier_ids = fields.Many2many(
        'res.users',
        'recap_caisses_wizard_user_rel',
        'wizard_id',
        'user_id',
        string='Caissiers',
        help="Auto-rempli selon la période et les postes sélectionnés",
    )

    # ------------------------------------------------------------------
    # Onchange : mise à jour automatique des caissiers
    # ------------------------------------------------------------------

    @api.onchange('date_from', 'date_to', 'config_ids', 'company_id')
    def _onchange_update_caissiers(self):
        if not self.date_from or not self.date_to or not self.company_id:
            self.caissier_ids = False
            return
        domain = [
            ('date_order', '>=', self._dt_from()),
            ('date_order', '<=', self._dt_to()),
            ('state', 'in', ['paid', 'invoiced', 'done']),
            ('company_id', '=', self.company_id.id),
            ('user_id', '!=', False),
        ]
        if self.config_ids:
            domain.append(('config_id', 'in', self.config_ids.ids))
        orders = self.env['pos.order'].search(domain)
        employees = orders.mapped('user_id')
        self.caissier_ids = [(6, 0, employees.ids)]

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('custom_reports.action_report_recap_caisses').report_action(self)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dt_from(self):
        return fields.Datetime.to_datetime(self.date_from)

    def _dt_to(self):
        return fields.Datetime.to_datetime(self.date_to).replace(
            hour=23, minute=59, second=59)

    def _get_orders(self):
        domain = [
            ('date_order', '>=', self._dt_from()),
            ('date_order', '<=', self._dt_to()),
            ('state', 'in', ['paid', 'invoiced', 'done']),
            ('company_id', '=', self.company_id.id),
        ]
        if self.config_ids:
            domain.append(('config_id', 'in', self.config_ids.ids))
        return self.env['pos.order'].search(domain)

    def _get_sessions(self):
        domain = [
            ('start_at', '>=', self._dt_from()),
            ('start_at', '<=', self._dt_to()),
            ('config_id.company_id', '=', self.company_id.id),
        ]
        if self.config_ids:
            domain.append(('config_id', 'in', self.config_ids.ids))
        return self.env['pos.session'].search(domain)

    def _order_ca(self, orders):
        lines = orders.mapped('lines').filtered(
            lambda l: not l.combo_parent_id and not l.is_reward_line
        )
        ca_ht = sum(l.price_subtotal for l in lines)
        ca_ttc = sum(l.price_subtotal_incl for l in lines)
        cout = sum(l.total_cost or 0.0 for l in lines)
        marge = ca_ht - cout
        pct_marge = round(marge / ca_ht * 100, 2) if ca_ht else 0.0
        pct_marque = round(marge / ca_ttc * 100, 2) if ca_ttc else 0.0
        return {
            'ca_ht': ca_ht, 'ca_ttc': ca_ttc, 'marge': marge,
            'pct_marge': pct_marge, 'pct_marque': pct_marque,
        }

    def _pmt_total(self, payments):
        return sum(payments.mapped('amount'))

    # ------------------------------------------------------------------
    # Données du rapport (PDF unique, toutes caisses combinées)
    # ------------------------------------------------------------------

    def get_report_data(self):
        self.ensure_one()

        all_orders = self._get_orders()
        sessions = self._get_sessions()

        # ================================================================
        # Section 1 – CA détaillé
        # ================================================================
        en_compte_order_ids = set(
            p.pos_order_id.id
            for p in self.env['pos.payment'].search([
                ('pos_order_id', 'in', all_orders.ids),
                ('payment_method_id.is_limit', '=', True),
            ])
        ) if all_orders else set()

        en_compte_orders = all_orders.filtered(lambda o: o.id in en_compte_order_ids)
        comptant_orders = all_orders.filtered(lambda o: o.id not in en_compte_order_ids)

        comptant_data = self._order_ca(comptant_orders)
        en_compte_data = self._order_ca(en_compte_orders)
        avoir_emis_data = {
            'ca_ht': 0.0, 'ca_ttc': 0.0, 'marge': 0.0,
            'pct_marge': 0.0, 'pct_marque': 0.0,
        }
        total_ca = {
            'ca_ht': comptant_data['ca_ht'] + en_compte_data['ca_ht'],
            'ca_ttc': comptant_data['ca_ttc'] + en_compte_data['ca_ttc'],
            'marge': comptant_data['marge'] + en_compte_data['marge'],
        }
        total_ca['pct_marge'] = round(
            total_ca['marge'] / total_ca['ca_ht'] * 100, 2) if total_ca['ca_ht'] else 0.0
        total_ca['pct_marque'] = round(
            total_ca['marge'] / total_ca['ca_ttc'] * 100, 2) if total_ca['ca_ttc'] else 0.0

        ca_detaille = {
            'comptant': comptant_data,
            'avoir_emis': avoir_emis_data,
            'en_compte_facture': en_compte_data,
            'total': total_ca,
        }

        # ================================================================
        # Section 2 – Encaissements / Décaissements
        # ================================================================
        session_ids = sessions.ids
        all_payments = self.env['pos.payment'].search(
            [('session_id', 'in', session_ids)] if session_ids else [('id', '=', False)]
        )

        especes_p = all_payments.filtered(lambda p: p.payment_method_id.is_cash_count)
        cheques_p = all_payments.filtered(lambda p: p.payment_method_id.is_cheque)
        cartes_p = all_payments.filtered(lambda p: p.payment_method_id.is_bank_card)
        titres_p = all_payments.filtered(lambda p: p.payment_method_id.is_titre_paiement)
        food_p = all_payments.filtered(lambda p: getattr(p.payment_method_id, 'is_food', False))
        loyalty_p = all_payments.filtered(lambda p: getattr(p.payment_method_id, 'is_loyalty', False))
        en_compte_p = all_payments.filtered(lambda p: p.payment_method_id.is_limit)

        fdc_init_especes = sum(sessions.mapped('cash_register_balance_start')) if sessions else 0.0
        prelev_especes = sum(sessions.mapped('prelevement_especes_amount')) if sessions else 0.0
        ecart_regl_total = sum(
            session.ecart_reglement or 0.0 for session in sessions
        ) if sessions else 0.0

        esp_amt = self._pmt_total(especes_p)
        chq_amt = self._pmt_total(cheques_p)
        crt_amt = self._pmt_total(cartes_p)
        tit_amt = self._pmt_total(titres_p)
        food_amt = self._pmt_total(food_p)
        loyalty_amt = self._pmt_total(loyalty_p)
        enc_amt = self._pmt_total(en_compte_p)

        def _row(fdc_init, comptants, prelev):
            total_enc = comptants
            total_dec = prelev
            fdc_final = fdc_init + total_enc - total_dec
            ecart = prelev - comptants
            return {
                'fdc_init': fdc_init, 'comptants': comptants,
                'total_enc': total_enc, 'prelev': prelev,
                'total_dec': total_dec, 'fdc_final': fdc_final, 'ecart': ecart,
            }

        rows = {
            'especes': _row(fdc_init_especes, esp_amt, prelev_especes),
            'cheques': _row(0.0, chq_amt, chq_amt),
            'cartes': _row(0.0, crt_amt, crt_amt),
            'titres': _row(0.0, tit_amt, tit_amt),
            'avoir': _row(0.0, food_amt, food_amt),
            'porte_monnaie': _row(0.0, loyalty_amt, loyalty_amt),
            'virements': _row(0.0, 0.0, 0.0),
            'ecart_regl': {
                'fdc_init': 0.0, 'comptants': 0.0, 'total_enc': 0.0,
                'prelev': 0.0, 'total_dec': 0.0, 'fdc_final': 0.0,
                'ecart': ecart_regl_total,
            },
        }

        def _sum_col(col):
            return sum(r[col] for r in rows.values())

        total1 = {
            'fdc_init': _sum_col('fdc_init'),
            'comptants': _sum_col('comptants'),
            'total_enc': _sum_col('total_enc'),
            'prelev': _sum_col('prelev'),
            'total_dec': _sum_col('total_dec'),
            'fdc_final': _sum_col('fdc_final'),
            'ecart': _sum_col('ecart'),
        }

        avoir_deduits = food_amt + loyalty_amt
        total2_enc = total1['total_enc'] - avoir_deduits
        total2_dec = total1['total_dec'] - avoir_deduits
        total2 = {
            'avoir_deduits': avoir_deduits,
            'acomptes_deduits': 0.0,
            'total_enc': total2_enc,
            'total_dec': total2_dec,
            'fdc_final': total1['fdc_final'],
        }

        avoirs_emis = 0.0
        mise_en_compte = enc_amt
        total_general = {
            'total_enc': total2_enc + avoirs_emis + mise_en_compte,
            'total_dec': total2_dec,
        }

        encaissements = {
            'rows': rows, 'total1': total1, 'total2': total2,
            'avoirs_emis': avoirs_emis,
            'mise_en_compte': mise_en_compte,
            'total_general': total_general,
        }

        # ================================================================
        # Section 3 – Répartition des encaissements
        # ================================================================
        enc_orders_set = en_compte_p.mapped('pos_order_id')
        esp_orders_set = especes_p.mapped('pos_order_id')
        tit_orders_set = titres_p.mapped('pos_order_id')
        total_orders_count = len(enc_orders_set) + len(esp_orders_set) + len(tit_orders_set)
        total_repartition_amt = mise_en_compte + esp_amt + tit_amt

        def _pct_count(n):
            return round(n / total_orders_count * 100, 2) if total_orders_count else 0.0

        def _pct_amt(a):
            return round(a / total_repartition_amt * 100, 2) if total_repartition_amt else 0.0

        repartition_encaissements = [
            {
                'label': 'Mis en compte',
                'count': len(enc_orders_set),
                'pct_count': _pct_count(len(enc_orders_set)),
                'montant': mise_en_compte,
                'pct_montant': _pct_amt(mise_en_compte),
            },
            {
                'label': 'Espèces',
                'count': len(esp_orders_set),
                'pct_count': _pct_count(len(esp_orders_set)),
                'montant': esp_amt,
                'pct_montant': _pct_amt(esp_amt),
            },
            {
                'label': 'Titre de paiement',
                'count': len(tit_orders_set),
                'pct_count': _pct_count(len(tit_orders_set)),
                'montant': tit_amt,
                'pct_montant': _pct_amt(tit_amt),
            },
        ]

        # ================================================================
        # Section 4 – Titres de paiements
        # ================================================================
        titres_detail = {}
        for payment in titres_p:
            name = payment.payment_method_id.name
            if name not in titres_detail:
                titres_detail[name] = {'count': 0, 'total': 0.0}
            titres_detail[name]['count'] += 1
            titres_detail[name]['total'] += payment.amount

        titres_detail_list = [
            {'name': n, 'count': d['count'], 'total': d['total']}
            for n, d in sorted(titres_detail.items())
        ]

        # ================================================================
        # Section 5 – Remises fidélités
        # ================================================================
        # Réductions : paiements effectués avec les points de fidélité (amount > 0)
        loyalty_reduction_p = loyalty_p.filtered(lambda p: p.amount > 0)
        montant_deduit = sum(loyalty_reduction_p.mapped('amount'))

        # Ajouts : rendu monnaie crédité sur la carte (stocké sur pos.order.rendu_monnaie)
        rendu_monnaie_orders = all_orders.filtered(lambda o: (o.rendu_monnaie or 0.0) > 0)
        nb_ajout = len(rendu_monnaie_orders)
        montant_ajout = sum(rendu_monnaie_orders.mapped('rendu_monnaie'))

        remises_fidelites = {
            'porte_monnaie_count': len(loyalty_reduction_p) + nb_ajout,
            'porte_monnaie_total': montant_deduit + montant_ajout,
            'nb_reduction': len(loyalty_reduction_p),
            'montant_deduit': montant_deduit,
            'nb_ajout': nb_ajout,
            'montant_ajout': montant_ajout,
        }

        # ================================================================
        # Section 6 – Répartition TVA
        # ================================================================
        all_lines = all_orders.mapped('lines').filtered(
            lambda l: not l.combo_parent_id and not l.is_reward_line
        )
        tax_breakdown = {}
        for line in all_lines:
            tax_pct = round(sum(line.tax_ids.mapped('amount')), 2) if line.tax_ids else 0.0
            if tax_pct not in tax_breakdown:
                tax_breakdown[tax_pct] = {
                    'ca_ttc': 0.0, 'base_ht': 0.0, 'tva': 0.0,
                    'articles_tenus': 0.0, 'articles_non_tenus': 0.0,
                    'tva_tenus': 0.0, 'tva_non_tenus': 0.0,
                }
            ca_ttc = line.price_subtotal_incl
            base_ht = line.price_subtotal
            tva = ca_ttc - base_ht
            tax_breakdown[tax_pct]['ca_ttc'] += ca_ttc
            tax_breakdown[tax_pct]['base_ht'] += base_ht
            tax_breakdown[tax_pct]['tva'] += tva
            is_storable = line.product_id.type in ['consu', 'product'] if line.product_id else False
            if is_storable:
                tax_breakdown[tax_pct]['articles_tenus'] += base_ht
                tax_breakdown[tax_pct]['tva_tenus'] += tva
            else:
                tax_breakdown[tax_pct]['articles_non_tenus'] += base_ht
                tax_breakdown[tax_pct]['tva_non_tenus'] += tva

        tva_repartition = []
        for tax_pct in sorted(tax_breakdown.keys()):
            d = tax_breakdown[tax_pct]
            base_calc = d['base_ht']
            tva_calc = round(base_calc * tax_pct / 100, 2)
            ecart = round(d['tva'] - tva_calc, 2)
            tva_repartition.append({
                'tax_percent': tax_pct,
                'ca_ttc': d['ca_ttc'],
                'base_ht': d['base_ht'],
                'articles_tenus': d['articles_tenus'],
                'articles_non_tenus': d['articles_non_tenus'],
                'tva': d['tva'],
                'tva_tenus': d['tva_tenus'],
                'tva_non_tenus': d['tva_non_tenus'],
                'base_calc': base_calc,
                'tva_calc': tva_calc,
                'ecart': ecart,
                'pct_ecart': round(ecart / d['tva'] * 100, 2) if d['tva'] else 0.0,
            })

        # ================================================================
        # En-tête
        # ================================================================
        configs = self.config_ids or self.env['pos.config'].search(
            [('company_id', '=', self.company_id.id)], order='name'
        )
        postes_names = ', '.join(configs.mapped('name')) if configs else 'Tous les postes'

        # Lieu = ville de la société
        lieu = self.company_id.city or self.company_id.street or ''

        # Caissiers sélectionnés dans le wizard
        caissiers_names = ', '.join(self.caissier_ids.mapped('name')) \
            if self.caissier_ids else 'Tous les caissiers'

        header = {
            'company_name': self.company_id.name,
            'postes': postes_names,
            'lieu': lieu,
            'caissiers': caissiers_names,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'print_date': date.today().strftime('%d/%m/%Y'),
        }

        return {
            'header': header,
            'ca_detaille': ca_detaille,
            'encaissements': encaissements,
            'repartition_encaissements': repartition_encaissements,
            'titres_detail': titres_detail_list,
            'remises_fidelites': remises_fidelites,
            'tva_repartition': tva_repartition,
        }
