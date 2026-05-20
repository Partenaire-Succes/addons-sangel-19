# -*- coding: utf-8 -*-
from odoo import fields, models
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

    def _get_product_price_and_data(self, product):
        """Prix affiché dans le widget catalogue.

        Si le fournisseur a un prix <= 0 (ou absent), on utilise le coût
        standard du produit (standard_price) comme prix de référence.
        """
        res = super()._get_product_price_and_data(product)
        if res.get('price', 0) <= 0 and product.standard_price > 0:
            res['price'] = product.standard_price
        return res

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        """Création / mise à jour d'une ligne depuis le catalogue.

        Après l'appel standard, si le prix résultant est <= 0 (fournisseur
        avec prix nul), on le remplace par le coût standard du produit.
        """
        result = super()._update_order_line_info(product_id, quantity, **kwargs)
        if result <= 0 and quantity > 0:
            product = self.env['product.product'].browse(product_id)
            if product.standard_price > 0:
                pol = self.order_line.filtered(
                    lambda l: l.product_id.id == product_id and not l.display_type
                )
                if pol:
                    pol.sorted('id')[-1].price_unit = product.standard_price
                    return product.standard_price
        return result
