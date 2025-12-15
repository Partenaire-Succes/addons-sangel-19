# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    """Inherits Stock move for scanning multi barcode"""
    _inherit = 'stock.move'

    scan_barcode = fields.Char(
        string='Code-barres',
        compute='_compute_scan_barcode',
        inverse='_inverse_scan_barcode',
        store=True,
    )

    @api.depends('sale_line_id', 'purchase_line_id')
    def _compute_scan_barcode(self):
        """For updating the Product Barcode field in delivery while it's
                generating from a Purchase order or sale order"""
        for stock in self:
            if stock.sale_line_id:
                stock.scan_barcode = stock.sale_line_id.scan_barcode
            if stock.purchase_line_id:
                stock.scan_barcode = stock.purchase_line_id.scan_barcode

    def _inverse_scan_barcode(self):
        """Inverse function for scan_barcode"""
        for stock in self:
            stock.scan_barcode = stock.scan_barcode

    @api.onchange('scan_barcode')
    def _onchange_scan_barcode(self):
        """For getting the scanned barcode product"""
        if self.scan_barcode:
            product = self.env['product.multiple.barcodes'].search(
                [('product_multi_barcode', '=', self.scan_barcode)])
            self.product_id = product.product_id.id
