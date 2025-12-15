
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'


    product_id = fields.Many2one(
        comodel_name='product.product',
        compute='_compute_product_tmp_id',
        string='Product',
        store=True,
    )

    multi_barcode_id = fields.Many2one(
        comodel_name='product.multiple.barcodes',
        string='Code-barres',
        domain="[('product_id', '=', product_id)]",
        store=True,
    )

    multi_barcode_ids = fields.Many2many(
        comodel_name='product.multiple.barcodes',
        string='Code-barres',
        compute='_compute_multi_barcode_ids',
        store=True,
    )

    product_tmp_id = fields.Many2one(
        comodel_name='product.template',
        compute='_compute_product_tmp_id',
        string='Product Template',
        store=True,
    )

    barcode = fields.Char(
        string='Code-barres',
        related='multi_barcode_id.product_multi_barcode',
        store=True,
    )

    @api.depends('product_tmpl_ids')
    def _compute_product_tmp_id(self):
        for record in self:
            if record.product_tmpl_ids:
                tmpl = record.product_tmpl_ids[0]  # le premier
                record.product_tmp_id = tmpl.id
                record.product_id = tmpl.product_variant_id.id
            else:
                record.product_tmp_id = False
                record.product_id = False


    @api.onchange('barcode')
    def _onchange_barcode(self):
        for rec in self:
            if rec.barcode:
                rec.product_id.barcode = rec.barcode


