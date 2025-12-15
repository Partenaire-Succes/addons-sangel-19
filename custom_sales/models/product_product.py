from odoo import models, fields, api,_, SUPERUSER_ID

class ProductProduct(models.Model):
    _inherit = "product.product"


    all_company_ids = fields.Many2many(
        'res.company',
        'product_product_all_company_rel',
        'product_tmpl_id',
        'company_id',
        string="Sociétés"
    )

    @api.model
    def search(self, args, **kwargs):
        """Limiter la visibilité selon all_company_ids si pas superuser."""
        if not self.env.su:
            user_companies = self.env.companies.ids
            args = [
                '|',
                ('all_company_ids', '=', False),
                ('all_company_ids', 'in', user_companies)
            ] + list(args)
        return super(ProductProduct, self).search(args, **kwargs)


