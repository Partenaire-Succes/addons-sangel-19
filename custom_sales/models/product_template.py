from odoo import models, fields, api,_, SUPERUSER_ID

class ProductTemplate(models.Model):
    _inherit = "product.template"


    allowed_company_ids = fields.Many2many(
        'res.company',
        'product_template_allowed_company_rel',
        'product_tmpl_id',
        'company_id',
        string="Sociétés"
    )

    @api.model
    def search(self, args, **kwargs):
        """Limiter la visibilité selon allowed_company_ids si pas superuser."""
        if not self.env.su:
            user_companies = self.env.companies.ids
            args = [
                '|',
                ('allowed_company_ids', '=', False),
                ('allowed_company_ids', 'in', user_companies)
            ] + list(args)
        return super(ProductTemplate, self).search(args, **kwargs)
