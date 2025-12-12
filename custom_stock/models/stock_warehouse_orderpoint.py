from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class StockWarehouseOrderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    def auto_update_supply(self):
        for orderpoint in self:
            primary_supplier = self.env['product.supplierinfo'].search([
                ('product_tmpl_id', '=', orderpoint.product_id.product_tmpl_id.id),
                ('primary', '=', True)
            ], limit=1)

            # Si on a trouvé un fournisseur principal → appliquer
            if primary_supplier:
                primary_supplier.with_context(orderpoint_id=orderpoint.id).action_set_supplier()
                continue

            # Sinon → essayer de prendre n’importe quel fournisseur
            fallback_supplier = self.env['product.supplierinfo'].search([
                ('product_tmpl_id', '=', orderpoint.product_id.product_tmpl_id.id)
            ], limit=1)

            if fallback_supplier:
                fallback_supplier.with_context(orderpoint_id=orderpoint.id).action_set_supplier()



class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    primary = fields.Boolean(
        string='Fournisseur principal',
        default=False,
        help="Cocher pour définir ce fournisseur comme principal pour ce produit"
    )

    @api.constrains('primary', 'product_tmpl_id')
    def _check_single_primary_supplier(self):
        """
        S'assure qu'il n'y a qu'un seul fournisseur principal par produit.
        """
        for supplier in self:
            if supplier.primary:
                other_primary = self.search([
                    ('product_tmpl_id', '=', supplier.product_tmpl_id.id),
                    ('primary', '=', True),
                    ('id', '!=', supplier.id)
                ])
                if other_primary:
                    # Retirer le flag primary des autres
                    other_primary.write({'primary': False})
                    _logger.info(
                        f"⚠️ Fournisseur principal remplacé pour "
                        f"'{supplier.product_tmpl_id.display_name}': "
                        f"{other_primary.mapped('partner_id.display_name')} → {supplier.partner_id.display_name}"
                    )