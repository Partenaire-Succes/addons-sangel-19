# -*- coding: utf-8 -*-
from odoo import models
from odoo.fields import Domain


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_add_from_catalog(self):
        res = super().action_add_from_catalog()
        list_view_id = self.env.ref('custom_purchase.product_view_list_catalog_purchase').id
        # Insère la vue liste après la vue kanban
        res['views'].insert(1, (list_view_id, 'list'))
        return res

    def _get_product_catalog_domain(self):
        # Exclut les produits avec statut magasin "D" pour la société courante.
        # Les produits sans statut défini pour ce magasin restent inclus (not any).
        return super()._get_product_catalog_domain() & Domain(
            'company_status_ids', 'not any', [
                ('company_id', '=', self.company_id.id),
                ('status_id.code', '=', 'D'),
            ]
        )
