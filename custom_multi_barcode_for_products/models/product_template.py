# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    """Inherits Product template for multi barcode feature"""
    _inherit = 'product.template'

    template_multi_barcode_ids = fields.One2many(
        comodel_name='product.multiple.barcodes',
        inverse_name='product_template_id',
        string='Code-barres multiples',
    )

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)
        if not self.env.context.get('skip_barcode_sync'):
            for template in self:
                if template.template_multi_barcode_ids:
                    template.template_multi_barcode_ids.update({
                        'product_id': template.product_variant_id.id
                    })
        return res

    @api.model_create_multi
    def create(self, vals):
        res = super(ProductTemplate, self).create(vals)
        for template in res:
            if template.template_multi_barcode_ids:
                template.template_multi_barcode_ids.update({
                    'product_id': template.product_variant_id.id
                })
        return res


