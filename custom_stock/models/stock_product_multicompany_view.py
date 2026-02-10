from odoo import api, fields, models


class StockProductMulticompanyTransient(models.TransientModel):
    _name = 'stock.product.multicompany'
    _description = 'Stock Multi-Sociétés (par variantes)'

    company_id = fields.Many2one(
        'res.company',
        string='Société',
        required=True,
    )

    product_ids = fields.Many2many(
        'product.product',
        string='Produits',
        required=True,
    )

    line_ids = fields.One2many(
        'stock.product.multicompany.line',
        'wizard_id',
        string='Stock',
        compute='_compute_stock_lines',
        store=False,
    )

    @api.depends('product_ids', 'company_id')
    def _compute_stock_lines(self):
        for wizard in self:
            wizard.line_ids = [(5, 0, 0)]

            if not wizard.company_id or not wizard.product_ids:
                continue

            lines = []
            for product in wizard.product_ids:

                qty = product.sudo().with_context(
                    allowed_company_ids=[wizard.company_id.id],
                    force_company=wizard.company_id.id,
                ).qty_available

                lines.append((0, 0, {
                    'product_id': product.id,
                    'qty_available': qty,
                }))

            wizard.line_ids = lines

class StockProductMulticompanyLine(models.TransientModel):
    _name = 'stock.product.multicompany.line'
    _description = 'Ligne stock multi-société'

    wizard_id = fields.Many2one(
        'stock.product.multicompany',
        ondelete='cascade'
    )

    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        readonly=True
    )

    qty_available = fields.Float(
        string='En stock',
        readonly=True
    )
