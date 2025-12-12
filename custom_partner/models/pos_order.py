from odoo import fields, models, api


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model_create_multi
    def create(self, vals_list):
        # Bloquer création depuis POS
        ctx = dict(self.env.context,
                   loyalty_no_mail=True,
                   tracking_disable=True,
                   from_pos=True)
        return super(PosOrder, self.with_context(ctx)).create(vals_list)

