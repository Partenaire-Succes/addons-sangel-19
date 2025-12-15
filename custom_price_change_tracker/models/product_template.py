from odoo import api, fields, models,_
import logging
_logger = logging.getLogger(__name__)



class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def write(self, vals):
        # Surveiller les changements de prix
        if 'list_price' in vals:
            for record in self:
                old_price = record.list_price
                new_price = vals['list_price']

                # Créer un enregistrement d'historique si le prix a changé
                if old_price != new_price:
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
        # Suivre les changements de prix pour les variantes de produits
        if 'lst_price' in vals:
            for record in self:
                old_price = record.lst_price
                new_price = vals['lst_price']

                # Ne créer l'historique que si le prix a réellement changé
                if old_price != new_price:
                    try:
                        self.env['product.price.history'].sudo().create({
                            'product_template_id': record.product_tmpl_id.id,
                            'product_id': record.id,
                            'old_price': old_price,
                            'new_price': new_price,
                        })

                        _logger.info(f"Changement de prix suivi pour {record.display_name}: {old_price} → {new_price}")

                    except Exception as e:
                        _logger.error(
                            f"Erreur lors du suivi du changement de prix pour {record.display_name}: {str(e)}")

        return super().write(vals)