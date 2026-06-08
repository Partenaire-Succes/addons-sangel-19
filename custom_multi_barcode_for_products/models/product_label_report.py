# -*- coding: utf-8 -*-
from odoo import models


class ReportProductLabel2x7(models.AbstractModel):
    _inherit = 'report.product.report_producttemplatelabel2x7'

    def _get_report_values(self, docids, data):
        result = super()._get_report_values(docids, data)
        result['data'] = data or {}
        result['is_grame'] = data.get('is_grame', False) if data else False
        result['unit_grame'] = data.get('unit_grame', 100.0) if data else 100.0
        return result
