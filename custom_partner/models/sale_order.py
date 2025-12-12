from odoo import fields, models, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        # Bloquer création depuis ventes
        ctx = dict(self.env.context, loyalty_no_mail=True, tracking_disable=True)
        return super(SaleOrder, self.with_context(ctx)).action_confirm()
