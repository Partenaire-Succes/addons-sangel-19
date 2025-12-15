# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    """Inherits Sale order line for scanning multi barcode"""
    _inherit = 'sale.order.line'

    scan_barcode = fields.Char(string='Code-barres')

    def _prepare_invoice_line(self, **optional_values):
        """For adding the scanned barcode in the invoice"""
        res = super()._prepare_invoice_line(**optional_values)
        res['scan_barcode'] = self.move_ids[:1].scan_barcode if self.move_ids else ''
        return res

    @api.onchange('scan_barcode')
    def _onchange_scan_barcode(self):
        """For getting the scanned barcode product"""
        if self.scan_barcode:
            product = self.env['product.multiple.barcodes'].search(
                [('product_multi_barcode', '=', self.scan_barcode)])
            self.product_id = product.product_id.id


