# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrderLines(models.Model):
    """Inherits Purchase order line for scanning multi barcode"""
    _inherit = "purchase.order.line"

    scan_barcode = fields.Char(string='Code-barres')

    @api.onchange('scan_barcode')
    def _onchange_scan_barcode(self):
        """For getting the scanned barcode product"""
        if self.scan_barcode:
            product = self.env['product.multiple.barcodes'].search(
                [('product_multi_barcode', '=', self.scan_barcode)])
            self.product_id = product.product_id.id
