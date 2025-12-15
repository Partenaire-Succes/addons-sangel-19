# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, _, Command
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round

class LoyaltyReward(models.Model):
    _inherit = "loyalty.reward"

    reward_same_product = fields.Boolean(
        string="Offrir le produit acheté",
        help="Si activé, le produit gratuit sera celui qui déclenche la condition."
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_reward_values_product(self, reward, coupon, product=None, **kwargs):
        """
        Surcharge pour permettre d'offrir le produit acheté
        """
        self.ensure_one()
        assert reward.reward_type == 'product'

        # --- Nouvelle logique ---
        if reward.reward_same_product:
            # On récupère le produit déclencheur depuis kwargs ou contexte
            product = product or kwargs.get('product')
            if not product:
                raise UserError(_('Aucun produit déclencheur trouvé pour appliquer la récompense.'))
            # S'assurer qu'on a bien un recordset product.product
            if not isinstance(product, models.BaseModel):
                product = self.env['product.product'].browse(product)

        else:
            # Logique native
            reward_products = reward.reward_product_ids
            product = product or reward_products[:1]
            if not product or product not in reward_products:
                raise UserError(_('Produit invalide pour réclamer la récompense.'))

        # Taxes et calcul des points
        taxes = self.fiscal_position_id.map_tax(
            product.taxes_id._filter_taxes_by_company(self.company_id)
        )
        points = self._get_real_points_for_coupon(coupon)
        claimable_count = (
            float_round(points / reward.required_points, precision_rounding=1, rounding_method='DOWN')
            if not reward.clear_wallet else 1
        )
        cost = points if reward.clear_wallet else claimable_count * reward.required_points

        return [{
            'name': _("Produit gratuit - %(product)s", product=product.with_context(display_default_code=False).display_name),
            'product_id': product.id,
            'discount': 100,
            'product_uom_qty': reward.reward_product_qty * claimable_count,
            'reward_id': reward.id,
            'coupon_id': coupon.id,
            'points_cost': cost,
            'reward_identifier_code': self.env['sale.order']._generate_random_reward_code(),
            'product_uom': product.uom_id.id,
            'sequence': max(self.order_line.filtered(lambda x: not x.is_reward_line).mapped('sequence'), default=10) + 1,
            'tax_id': [(Command.CLEAR, 0, 0)] + [(Command.LINK, tax.id, False) for tax in taxes]
        }]
