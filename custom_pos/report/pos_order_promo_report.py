# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaires Succes.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com/>)
#    Author: Adama KONE
#
#############################################################################
from odoo import api, fields, models, tools


class PosOrderPromoReport(models.Model):
    """
    SQL View report for POS promo/discount/loyalty sales analysis.
    Shows all order lines that have:
    - Loyalty rewards (is_reward_line = True)
    - Manual discounts (discount > 0)
    - Coupons applied (coupon_id IS NOT NULL)
    """
    _name = 'report.pos.order.promo'
    _description = 'Rapport des ventes promo POS'
    _auto = False
    _order = 'date desc'

    # Date & Commande
    date = fields.Datetime(string='Date de commande', readonly=True)
    order_id = fields.Many2one('pos.order', string='Commande', readonly=True)
    session_id = fields.Many2one('pos.session', string='Session', readonly=True)
    config_id = fields.Many2one('pos.config', string='Point de vente', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Client', readonly=True)
    company_id = fields.Many2one('res.company', string='Société', readonly=True)
    user_id = fields.Many2one('res.users', string='Vendeur', readonly=True)

    # Info Produit
    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Modèle de produit', readonly=True)
    categ_id = fields.Many2one('product.category', string='Catégorie de produit', readonly=True)

    # Quantités
    qty = fields.Float(string='Quantité', readonly=True)

    # Prix
    original_price = fields.Float(string='Prix original', readonly=True,
                                   help='Prix avant remise TTC (qté × prix unitaire × taux TVA)')
    promo_price = fields.Float(string='Prix promo', readonly=True,
                                help='Prix réellement payé TTC après remise')
    discount_amount = fields.Float(string='Montant remise', readonly=True,
                                    help='Montant économisé (original - promo)')
    discount_percent = fields.Float(string='Remise %', readonly=True,
                                     help='Pourcentage de remise appliqué')

    # Coûts & Marges
    total_cost = fields.Float(string='Coût total', readonly=True)
    margin = fields.Float(string='Marge', readonly=True,
                          help='Bénéfice (prix promo - coût)')
    margin_percent = fields.Float(string='Marge %', readonly=True,
                                   help='Marge en pourcentage du prix promo')

    # Info Promo
    is_reward_line = fields.Boolean(string='Ligne récompense', readonly=True)
    reward_id = fields.Many2one('loyalty.reward', string='Récompense', readonly=True)
    coupon_id = fields.Many2one('loyalty.card', string='Coupon', readonly=True)
    promo_type = fields.Selection([
        ('reward', 'Récompense fidélité'),
        ('discount', 'Remise manuelle'),
        ('coupon', 'Coupon'),
    ], string='Type de promo', readonly=True)

    def _select(self):
        """
        SQL View that shows SOURCE products instead of reward products.
        
        For orders with loyalty rewards:
        - Shows the actual products purchased (not "Carte-cadeau" or "10% sur produits spécifiques")
        - Allocates the reward discount proportionally to each source product
        
        For manual discounts:
        - Shows products that have discount > 0 applied directly
        """
        return """
            WITH 
            -- Identify orders that have reward lines and calculate total reward discount
            reward_orders AS (
                SELECT 
                    rl.order_id,
                    SUM(ABS(rl.price_subtotal_incl)) AS total_reward_discount,
                    MIN(rl.reward_id) AS first_reward_id,
                    MIN(rl.coupon_id) AS first_coupon_id
                FROM pos_order_line rl
                WHERE COALESCE(rl.is_reward_line, FALSE) = TRUE
                GROUP BY rl.order_id
            ),
            -- Calculate total value of source lines per order (for proportional allocation)
            source_line_totals AS (
                SELECT 
                    sl.order_id,
                    SUM(sl.price_subtotal_incl) AS total_source_value
                FROM pos_order_line sl
                WHERE COALESCE(sl.is_reward_line, FALSE) = FALSE
                  AND sl.price_subtotal_incl > 0
                GROUP BY sl.order_id
            )
            SELECT
                l.id AS id,
                s.date_order AS date,
                s.id AS order_id,
                s.session_id AS session_id,
                ps.config_id AS config_id,
                s.partner_id AS partner_id,
                s.company_id AS company_id,
                s.user_id AS user_id,
                l.product_id AS product_id,
                pt.id AS product_tmpl_id,
                pt.categ_id AS categ_id,
                l.qty AS qty,
                -- Original price TTC: reverse the discount to get price before reduction
                -- Formula from Odoo: original = price_subtotal_incl / (1 - discount/100)
                CASE 
                    WHEN l.discount > 0 AND l.discount < 100 
                    THEN ROUND(l.price_subtotal_incl / (1.0 - l.discount / 100.0), 2)
                    ELSE l.price_subtotal_incl
                END 
                + COALESCE(
                    -- Add allocated portion of reward discount for lines in rewarded orders
                    CASE 
                        WHEN slt.total_source_value > 0 AND ro.total_reward_discount > 0
                        THEN ro.total_reward_discount * (l.price_subtotal_incl / slt.total_source_value)
                        ELSE 0
                    END, 0
                ) AS original_price,
                -- Promo price = what customer actually paid (TTC)
                l.price_subtotal_incl AS promo_price,
                -- Discount amount = original - promo (calculated inline for accuracy)
                CASE 
                    WHEN l.discount > 0 AND l.discount < 100 
                    THEN ROUND(l.price_subtotal_incl / (1.0 - l.discount / 100.0), 2) - l.price_subtotal_incl
                    ELSE 0
                END 
                + COALESCE(
                    CASE 
                        WHEN slt.total_source_value > 0 AND ro.total_reward_discount > 0
                        THEN ro.total_reward_discount * (l.price_subtotal_incl / slt.total_source_value)
                        ELSE 0
                    END, 0
                ) AS discount_amount,
                -- Discount percent = discount field + allocated reward percent
                COALESCE(l.discount, 0) + COALESCE(
                    CASE 
                        WHEN slt.total_source_value > 0 AND ro.total_reward_discount > 0
                        THEN ROUND((ro.total_reward_discount * (l.price_subtotal_incl / slt.total_source_value)) / 
                             NULLIF(l.price_subtotal_incl / (1.0 - COALESCE(l.discount, 0) / 100.0), 0) * 100, 2)
                        ELSE 0
                    END, 0
                ) AS discount_percent,
                COALESCE(l.total_cost, 0) AS total_cost,
                l.price_subtotal_incl - COALESCE(l.total_cost, 0) AS margin,
                CASE 
                    WHEN l.price_subtotal_incl > 0 
                    THEN ROUND(((l.price_subtotal_incl - COALESCE(l.total_cost, 0)) / l.price_subtotal_incl) * 100, 2)
                    ELSE 0
                END AS margin_percent,
                -- Mark if this line benefits from a reward
                CASE WHEN ro.order_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_reward_line,
                ro.first_reward_id AS reward_id,
                COALESCE(l.coupon_id, ro.first_coupon_id) AS coupon_id,
                CASE
                    WHEN ro.order_id IS NOT NULL THEN 'reward'
                    WHEN l.coupon_id IS NOT NULL THEN 'coupon'
                    WHEN l.discount > 0 THEN 'discount'
                    ELSE NULL
                END AS promo_type
        """

    def _from(self):
        return """
            FROM pos_order_line l
            JOIN pos_order s ON s.id = l.order_id
            JOIN pos_session ps ON ps.id = s.session_id
            JOIN product_product pp ON pp.id = l.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN reward_orders ro ON ro.order_id = l.order_id
            LEFT JOIN source_line_totals slt ON slt.order_id = l.order_id
        """

    def _where(self):
        """
        Filter to show:
        1. Source products from orders that have rewards (excluding reward lines themselves)
        2. Products with manual discounts
        Exclude reward lines - we show the source products instead.
        """
        return """
            WHERE COALESCE(l.is_reward_line, FALSE) = FALSE
            AND (
                -- Order has reward lines applied
                ro.order_id IS NOT NULL
                -- Or line has manual discount
                OR l.discount > 0 
                -- Or line has coupon directly applied
                OR l.coupon_id IS NOT NULL
            )
            AND s.state NOT IN ('cancel', 'draft')
            AND l.price_subtotal_incl >= 0
        """

    def _group_by(self):
        """No grouping needed - we show individual lines with allocated discounts."""
        return ""

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
                %s
            )
        """ % (self._table, self._select(), self._from(), self._where(), self._group_by()))
