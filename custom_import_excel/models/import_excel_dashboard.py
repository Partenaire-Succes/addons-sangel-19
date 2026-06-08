# -*- coding: utf-8 -*-
from odoo import models


class ImportExcelDashboard(models.TransientModel):
    _name = 'import.excel.dashboard'
    _description = 'Import Excel — Tableau de bord'

    def _open_wizard(self, model):
        return {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_stock_import(self):
        return self._open_wizard('stock.excel.import.wizard')

    def action_open_fix_price(self):
        return self._open_wizard('fix.price.inventory.wizard')

    def action_open_orderpoint(self):
        return self._open_wizard('orderpoint.import.wizard')

    def action_open_barcodes(self):
        return self._open_wizard('import.barcodes.wizard')

    def action_open_supplier_price(self):
        return self._open_wizard('supplier.price.import.wizard')

    def action_open_loyalty(self):
        return self._open_wizard('import.loyalty.points.wizard')

    def action_open_limit_credit(self):
        return self._open_wizard('import.limit.credit.wizard')

    def action_open_pos_history(self):
        return self._open_wizard('pos.history.import.wizard')

    def action_open_avco(self):
        return self._open_wizard('stock.avco.import.wizard')

    def action_open_pos_margin(self):
        return self._open_wizard('pos.margin.cost.wizard')

    def action_open_product_status(self):
        return self._open_wizard('product.status.import.wizard')
