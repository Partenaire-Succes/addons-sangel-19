from odoo import api, fields, models,_
import logging
_logger = logging.getLogger(__name__)



class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        for record in self:
            old_price = record.list_price
            new_price = vals.get('list_price', record.list_price)

            product_type = vals.get('type', record.type)
            code = vals.get('default_code', record.default_code)

            # Vérifier si le prix change + produit consu + code existant
            if (
                old_price != new_price
                and product_type == 'consu'
                and code
            ):
                self.env['product.price.history'].create({
                    'product_id': record.id,
                    'old_price': old_price,
                    'new_price': new_price,
                    'date_changed': fields.Datetime.now(),
                    'user_id': self.env.user.id,
                })

        return super(ProductTemplate, self).write(vals)



class ProductProduct(models.Model):
    _inherit = 'product.product'

    def write(self, vals):
        for record in self:
            old_price = record.lst_price
            new_price = vals.get('lst_price', record.lst_price)

            product_type = vals.get('type', record.type)
            code = vals.get('default_code', record.default_code)

            # Vérifier si le prix change + produit consu + barcode existant
            if old_price != new_price and product_type == 'consu' and code:
                try:
                    self.env['product.price.history'].sudo().create({
                        'product_template_id': record.product_tmpl_id.id,
                        'product_id': record.id,
                        'old_price': old_price,
                        'new_price': new_price,
                    })

                    _logger.info(
                        f"Changement de prix suivi pour {record.display_name}: {old_price} → {new_price}"
                    )

                except Exception as e:
                    _logger.error(
                        f"Erreur lors du suivi du changement de prix pour {record.display_name}: {str(e)}"
                    )

        return super().write(vals)