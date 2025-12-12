from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    family_loyalty = fields.Selection(related='categ_id.family_loyalty', readonly=True, store=True)

    is_eligible = fields.Boolean(
        string='Éligible aux points de fidélité',
        default=True,
        help="Si coché, ce produit peut générer des points de fidélité"
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    family_loyalty = fields.Selection(related='categ_id.family_loyalty', readonly=True, store=True)
    is_eligible = fields.Boolean(
        related='product_tmpl_id.is_eligible',
        readonly=False,
        store=True
    )
    
    def _load_pos_data_fields(self, config_id):
        """Ajouter family_loyalty et is_eligible aux champs du POS"""
        result = super()._load_pos_data_fields(config_id)
        result.append('family_loyalty')
        result.append('is_eligible')
        return result
    

class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    family_loyalty = fields.Selection([
        ('none', 'Pas de points de fidélité'),
        ('200', '1 point / 200 F'),
        ('1000', '1 point / 1000 F'),
    ],default='none', string='Famille Fidélité', help="Définit le ratio de points de fidélité pour cette catégorie de produits")