# -*- coding: utf-8 -*-
from datetime import datetime, time
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class AvoirJourneeWizard(models.TransientModel):
    """
    Rapport Avoir Journée — Crédit Alimentaire.

    Regroupe les commandes POS payées (au moins partiellement) en crédit
    alimentaire sur une plage de dates, groupées par catégorie client.

    Structure du rapport :
      Catégorie A
        DATE | N° CLIENT | NOM | N° FACTURE | MONTANT
        ...
        TOTAL catégorie A
      Catégorie B
        ...
      TOTAL GÉNÉRAL
    """
    _name = 'avoir.journee.wizard'
    _description = 'Rapport Avoir Journée — Crédit Alimentaire'

    date_debut = fields.Date(
        string='Date début',
        required=True,
        default=fields.Date.today,
    )
    date_fin = fields.Date(
        string='Date fin',
        required=True,
        default=fields.Date.today,
    )
    category_ids = fields.Many2many(
        'res.partner.category',
        string='Catégories client',
        help="Laisser vide pour inclure toutes les catégories.",
    )
    mode_payment = fields.Many2one(
        'pos.payment.method',
        string='Mode de paiement',
        default=lambda self: self._get_food_payment_methods(),
        help="Laisser vide pour inclure tous les modes de paiement.",
    )

    # ── Helpers internes ─────────────────────────────────────────────────────

    def _get_food_payment_methods(self):
        """Retourne les méthodes de paiement 'Crédit Alimentaire' (is_food=True)."""
        return self.env['pos.payment.method'].search([('is_food', '=', True)])

    def _get_food_credit_orders(self):
        """
        Retourne les pos.order validés, avec un partenaire identifié,
        ayant au moins un paiement en crédit alimentaire dans la période.
        """
        food_methods = self.mode_payment
        if not food_methods:
            return self.env['pos.order']

        dt_debut = datetime.combine(self.date_debut, time.min)
        dt_fin   = datetime.combine(self.date_fin,   time.max)

        payments = self.env['pos.payment'].search([
            ('payment_method_id', '=', food_methods.id),
            ('pos_order_id.date_order', '>=', dt_debut),
            ('pos_order_id.date_order', '<=', dt_fin),
            ('pos_order_id.state', 'not in', ('draft', 'cancel')),
            ('pos_order_id.partner_id', '!=', False),
        ])
        return payments.mapped('pos_order_id')

    # ── Données pour le rapport ───────────────────────────────────────────────

    def get_data_by_category(self):
        """
        Retourne une liste de dicts triés par catégorie, puis par client :
        [
          {
            'name': 'MUNEST',
            'sort_key': 'MUNEST',
            'clients': [
              {
                'customer_id':  '10001234',
                'partner_name': 'CYRELLE DONATIEN',
                'lines': [
                  {'date': datetime, 'order_name': '04-3-29951', 'amount': 3800.0},
                  ...
                ],
                'subtotal': 7855.0,
              }, ...
            ],
            'total': 34055.0,
          }, ...
        ]
        """
        orders = self._get_food_credit_orders()
        # result[cat_key]['clients'][partner_id] = {customer_id, partner_name, lines, subtotal}
        result = {}

        for order in orders:
            food_amount = sum(
                p.amount for p in order.payment_ids
                if p.payment_method_id == self.mode_payment
            )
            if food_amount <= 0:
                continue

            partner    = order.partner_id
            categories = partner.category_id

            if self.category_ids:
                categories = categories & self.category_ids
                if not categories:
                    continue

            target_cats = categories or self.env['res.partner.category']

            if not target_cats:
                # Client sans catégorie → groupe générique
                self._add_to_result(result, 0, 'SANS CATÉGORIE', 'ZZZZZ',
                                    partner, order, food_amount)
            else:
                for cat in target_cats:
                    self._add_to_result(result, cat.id, cat.name.upper(), cat.name.upper(),
                                        partner, order, food_amount)

        # Finalisation : dict clients → liste triée par nom client
        final = []
        for cat_data in sorted(result.values(), key=lambda x: x['sort_key']):
            clients_list = sorted(
                cat_data['clients'].values(),
                key=lambda c: (c['customer_id'], c['partner_name'])
            )
            for client in clients_list:
                client['lines'].sort(key=lambda l: (l['date'], l['order_name']))
            final.append({
                'name':     cat_data['name'],
                'sort_key': cat_data['sort_key'],
                'clients':  clients_list,
                'total':    cat_data['total'],
            })
        return final

    def _add_to_result(self, result, cat_key, cat_name, sort_key, partner, order, food_amount):
        """Insère une ligne dans la structure result[cat_key]['clients'][partner_id]."""
        if cat_key not in result:
            result[cat_key] = {
                'name':     cat_name,
                'sort_key': sort_key,
                'clients':  {},
                'total':    0.0,
            }
        pid = partner.id
        if pid not in result[cat_key]['clients']:
            result[cat_key]['clients'][pid] = {
                'customer_id':  partner.customer_id or '—',
                'partner_name': partner.name or '—',
                'lines':        [],
                'subtotal':     0.0,
            }
        result[cat_key]['clients'][pid]['lines'].append({
            'date':       order.date_order,
            'order_name': order.name or '—',
            'amount':     food_amount,
        })
        result[cat_key]['clients'][pid]['subtotal'] += food_amount
        result[cat_key]['total'] += food_amount

    def get_grand_total(self):
        return sum(c['total'] for c in self.get_data_by_category())

    # ── Labels d'en-tête ────────────────────────────────────────────────────

    def get_titre_label(self):
        if self.mode_payment:
            return 'Rapport de mode paiement — %s' % self.mode_payment.name
        return 'Rapport de mode paiement — Tous modes de paiement'

    def get_periode_label(self):
        if self.date_debut == self.date_fin:
            return 'DU %s' % self.date_debut.strftime('%d/%m/%Y')
        return 'DU %s AU %s' % (
            self.date_debut.strftime('%d/%m/%Y'),
            self.date_fin.strftime('%d/%m/%Y'),
        )

    def get_date_edition(self):
        return fields.Datetime.now().strftime('%d/%m/%Y %H:%M')

    # ── Action ──────────────────────────────────────────────────────────────

    def action_imprimer(self):
        self.ensure_one()
        if self.date_fin < self.date_debut:
            raise UserError(_("La date de fin ne peut pas être antérieure à la date de début."))
        if not self.mode_payment:
            raise UserError(_(
                "Veuillez sélectionner un mode de paiement."
            ))
        data = self.get_data_by_category()
        if not data:
            raise UserError(_(
                "Aucun passage trouvé pour la période sélectionnée.\n"
                "Vérifiez les dates, le mode de paiement ou les catégories client."
            ))
        return self.env.ref(
            'custom_pos.action_report_avoir_journee'
        ).report_action(self)
