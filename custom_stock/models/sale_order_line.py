from odoo import fields, models, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    code_article = fields.Char(string="Code Article")

    @api.onchange('code_article')
    def _onchange_code_article(self):
        if self.code_article:
            product = self.env['product.product'].search(
                [('product_tmpl_id.code_article', '=', self.code_article)],
                limit=1
            )
            if product:
                self.product_id = product.id

    @api.onchange('product_template_id')
    def _onchange_product_template_id(self):
        if self.product_template_id:
            if self.product_template_id.code_article:
                self.code_article = self.product_template_id.code_article
            else:
                self.code_article = False
