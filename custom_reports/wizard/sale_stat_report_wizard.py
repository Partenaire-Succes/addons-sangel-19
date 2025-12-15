# -*- coding: utf-8 -*-
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

    @api.constrains('date_start_period1', 'date_end_period1', 'date_start_period2', 'date_end_period2')
    def _check_dates(self):
        for record in self:
            if record.date_start_period1 > record.date_end_period1:
                raise UserError("La date de début de la période 1 doit être avant la date de fin.")
            if record.date_start_period2 > record.date_end_period2:
                raise UserError("La date de début de la période 2 doit être avant la date de fin.")

    def get_sale_data_by_category(self):
        """Retourne un dictionnaire des ventes groupées par catégorie client."""
        self.ensure_one()

        SaleOrder = self.env['sale.order']

        # Domaine de base
        domain_base = [
            ('state', 'in', ['sale', 'done']),
            ('company_id', '=', self.company_id.id),
        ]


        if self.partner_ids:
            domain_base.append(('partner_id', 'in', self.partner_ids.ids))

        # Domaines période 1 & 2
        domain_p1 = domain_base + [
            ('date_order', '>=', fields.Datetime.to_datetime(self.date_start_period1)),
            ('date_order', '<=',
             fields.Datetime.to_datetime(self.date_end_period1).replace(hour=23, minute=59, second=59)),
        ]
        domain_p2 = domain_base + [
            ('date_order', '>=', fields.Datetime.to_datetime(self.date_start_period2)),
            ('date_order', '<=',
             fields.Datetime.to_datetime(self.date_end_period2).replace(hour=23, minute=59, second=59)),
        ]

        orders_p1 = SaleOrder.search(domain_p1)
        print("orders_p1", orders_p1)
        orders_p2 = SaleOrder.search(domain_p2)
        print("orders_p2", orders_p2)

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
                    'partner_name': partner.name,
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
            margin = getattr(order, 'margin', 0.0)

            if period == 1:
                data['qty_p1'] += 1
                data['ca_p1'] += order.amount_untaxed
                data['margin_p1'] += margin

                cat_data['total_p1_qty'] += 1
                cat_data['total_p1_ca'] += order.amount_untaxed
                cat_data['total_p1_margin'] += margin
            else:
                data['qty_p2'] += 1
                data['ca_p2'] += order.amount_untaxed
                data['margin_p2'] += margin

                cat_data['total_p2_qty'] += 1
                cat_data['total_p2_ca'] += order.amount_untaxed
                cat_data['total_p2_margin'] += margin

        # Traiter toutes les commandes
        for o in orders_p1:
            add_order(o, 1)
        for o in orders_p2:
            add_order(o, 2)

        # Calcul des marges % et progressions
        for cat_key, cat_data in categories_data.items():
            for partner_id, vals in cat_data['clients'].items():
                # Marges en %
                if vals['ca_p1'] > 0:
                    vals['margin_pct_p1'] = (vals['margin_p1'] / vals['ca_p1']) * 100
                if vals['ca_p2'] > 0:
                    vals['margin_pct_p2'] = (vals['margin_p2'] / vals['ca_p2']) * 100

                # Progressions
                vals['prog_qty'] = vals['qty_p2'] - vals['qty_p1']
                vals['prog_ca'] = vals['ca_p2'] - vals['ca_p1']
                vals['prog_margin'] = vals['margin_p2'] - vals['margin_p1']

                # Progressions en %
                if vals['ca_p1'] > 0:
                    vals['prog_ca_pct'] = (vals['prog_ca'] / vals['ca_p1']) * 100
                else:
                    vals['prog_ca_pct'] = 100.0 if vals['ca_p2'] > 0 else 0.0

                if vals['margin_p1'] > 0:
                    vals['prog_margin_pct'] = (vals['prog_margin'] / vals['margin_p1']) * 100
                else:
                    vals['prog_margin_pct'] = 100.0 if vals['margin_p2'] > 0 else 0.0

            # Marges % totales par catégorie
            if cat_data['total_p1_ca'] > 0:
                cat_data['total_p1_margin_pct'] = (cat_data['total_p1_margin'] / cat_data['total_p1_ca']) * 100
            else:
                cat_data['total_p1_margin_pct'] = 0.0

            if cat_data['total_p2_ca'] > 0:
                cat_data['total_p2_margin_pct'] = (cat_data['total_p2_margin'] / cat_data['total_p2_ca']) * 100
            else:
                cat_data['total_p2_margin_pct'] = 0.0

            # Progressions totales
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
        """Générer le rapport PDF"""
        self.ensure_one()
        return self.env.ref('custom_reports.action_report_sale_statistics').report_action(self)