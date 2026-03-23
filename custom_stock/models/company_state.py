from odoo import models, fields

class ProductStatus(models.Model):
    _name = 'product.status'
    _description = 'Statut produit'
    _order = 'code'
    _rec_name = 'code'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('unique_code', 'unique(code)', 'Le code du statut doit être unique.')
    ]


class ProductCompanyStatus(models.Model):
    _name = 'product.company.status'
    _description = 'Statut produit par société'
    _rec_name = 'product_id'
    _order = 'product_id, company_id'

    product_id = fields.Many2one(
        'product.template',
        required=True,
        ondelete='cascade',
        index=True
    )

    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )

    status_id = fields.Many2one(
        'product.status',
        required=True
    )

    _sql_constraints = [
        (
            'uniq_product_company',
            'unique(product_id, company_id)',
            'Un seul statut par produit et par magasin.'
        )
    ]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    company_status_ids = fields.One2many(
        'product.company.status',
        'product_id',
        string='Statuts par magasin'
    )

    current_company_status_id = fields.Many2one(
        'product.status',
        string="Statut (magasin courant)",
        compute="_compute_current_company_status",
        inverse="_inverse_current_company_status",
        store=False
    )

    def _compute_current_company_status(self):
        for product in self:
            line = self.env['product.company.status'].search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            product.current_company_status_id = line.status_id if line else False

    def _inverse_current_company_status(self):
        for product in self:
            line = self.env['product.company.status'].search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

            if product.current_company_status_id:
                if line:
                    line.status_id = product.current_company_status_id
                else:
                    self.env['product.company.status'].create({
                        'product_id': product.id,
                        'company_id': self.env.company.id,
                        'status_id': product.current_company_status_id.id
                    })
            elif line:
                line.unlink()


class ProductProduct(models.Model):
    _inherit = 'product.product'

    current_company_status_id = fields.Many2one(
        'product.status',
        string="Statut (magasin courant)",
        related='product_tmpl_id.current_company_status_id',
        store=False,
        readonly=True
    )