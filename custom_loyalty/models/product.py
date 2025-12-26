from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    family_loyalty_id = fields.Many2one(
        related='categ_id.family_loyalty_id',
        readonly=True,
        store=True,
        string='Famille Fidélité',
    )

    is_eligible = fields.Boolean(
        string='Éligible aux points de fidélité',
        default=True,
        help="Si coché, ce produit peut générer des points de fidélité"
    )


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    family_loyalty_id = fields.Many2one(
        related='categ_id.family_loyalty_id',
        readonly=True,
        store=True,
        string='Famille Fidélité',
    )
    is_eligible = fields.Boolean(
        related='product_tmpl_id.is_eligible',
        readonly=False,
        store=True
    )
    
    def _load_pos_data_fields(self, config_id):
        """Ajouter family_loyalty_id et is_eligible aux champs du POS"""
        result = super()._load_pos_data_fields(config_id)
        result.append('family_loyalty_id')
        result.append('is_eligible')
        return result
    

class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    family_loyalty_id = fields.Many2one(
        'loyalty.family',
        string='Famille Fidélité',
        help="Définit le ratio de points de fidélité pour cette catégorie de produits. "
             "Laissez vide pour désactiver les points de fidélité.",
        ondelete='set null',
    )