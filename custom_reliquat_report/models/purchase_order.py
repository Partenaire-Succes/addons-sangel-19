from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    satisfaction_rate = fields.Float(
        string='Taux de satisfaction',
        compute='_compute_satisfaction_rate',
        store=True
    )

    @api.depends('order_line.qty_received', 'order_line.product_qty')
    def _compute_satisfaction_rate(self):
        for order in self:
            total_ordered = sum(line.product_qty for line in order.order_line)
            total_received = sum(line.qty_received for line in order.order_line)

            if total_ordered > 0:
                order.satisfaction_rate = total_received / total_ordered
            else:
                order.satisfaction_rate = 0.0
