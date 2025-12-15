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
        """Updating the multi barcodes"""
        res = super(ProductTemplate, self).write(vals)
        if self.template_multi_barcode_ids:
            self.template_multi_barcode_ids.update({
                'product_id': self.product_variant_id.id
            })

        if self.env.context.get('skip_barcode_sync'):
            return super(ProductTemplate, self).write(vals)

        return res

    @api.model_create_multi
    def create(self, vals):
        """Creating the multi barcodes"""
        res = super(ProductTemplate, self).create(vals)
        res.template_multi_barcode_ids.update({
            'product_id': res.product_variant_id.id
        })
        return res


