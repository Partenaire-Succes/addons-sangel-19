# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # ── Validation serveur (bloque imports/API en plus de l'UI) ─────────────

    # @api.constrains('product_id')
    # def _check_product_purchasable(self):
    #     for line in self.filtered('product_id'):
    #         tmpl = line.product_id.product_tmpl_id
    #         company = line.company_id or self.env.company

    #         # 1. Statut article X3
    #         if tmpl.actif_x3 and tmpl.actif_x3 != '1':
    #             raise UserError(_(
    #                 "Le produit « %s » ne peut pas être commandé : "
    #                 "son statut article X3 est « %s » (seul le statut Actif est autorisé).",
    #                 tmpl.display_name,
    #                 dict(tmpl._fields['actif_x3'].selection).get(tmpl.actif_x3, tmpl.actif_x3),
    #             ))

    #         # 2. Statut magasin courant (via table product.company.status)
    #         company_status = self.env['product.company.status'].search([
    #             ('product_id', '=', tmpl.id),
    #             ('company_id', '=', company.id),
    #         ], limit=1)
    #         if company_status and company_status.status_id.code == 'D':
    #             raise UserError(_(
    #                 "Le produit « %s » ne peut pas être commandé dans ce magasin : "
    #                 "son statut magasin est « %s » (code D — article désactivé pour ce site).",
    #                 tmpl.display_name,
    #                 company_status.status_id.name or 'D',
    #             ))

    # ── Avertissement UX lors de la sélection dans le formulaire ────────────

    def _compute_price_unit_and_date_planned_and_name(self):
        """Fallback coût produit quand le fournisseur a prix = 0.

        Odoo standard : si fournisseur trouvé → price_unit = seller.price (même si 0).
        Ce fallback : si price_unit reste 0 après le compute et que le produit
        a un coût standard > 0, on l'utilise comme prix de référence.
        Aucun accès à product_uom ou _select_seller pour éviter les incompatibilités.
        """
        super()._compute_price_unit_and_date_planned_and_name()
        for line in self:
            if line.price_unit or not line.product_id or not line.company_id:
                continue
            standard_price = line.product_id.with_company(line.company_id).standard_price
            if standard_price > 0:
                line.price_unit = standard_price

    @api.onchange('product_id')
    def _onchange_product_id_check_status(self):
        if not self.product_id:
            return
        tmpl = self.product_id.product_tmpl_id
        company = self.company_id or self.env.company

        # Statut article X3
        if tmpl.actif_x3 and tmpl.actif_x3 != '1':
            label = dict(tmpl._fields['actif_x3'].selection).get(tmpl.actif_x3, tmpl.actif_x3)
            self.product_id = False
            return {
                'warning': {
                    'title': _("Produit non autorisé"),
                    'message': _(
                        "« %s » ne peut pas être commandé.\n"
                        "Statut X3 : %s (seul Actif est autorisé).",
                        tmpl.display_name, label,
                    ),
                }
            }

        # Statut magasin
        company_status = self.env['product.company.status'].search([
            ('product_id', '=', tmpl.id),
            ('company_id', '=', company.id),
        ], limit=1)
        if company_status and company_status.status_id.code == 'D':
            self.product_id = False
            return {
                'warning': {
                    'title': _("Produit désactivé pour ce magasin"),
                    'message': _(
                        "« %s » ne peut pas être commandé dans ce magasin.\n"
                        "Statut magasin : %s (code D).",
                        tmpl.display_name,
                        company_status.status_id.name or 'D',
                    ),
                }
            }
