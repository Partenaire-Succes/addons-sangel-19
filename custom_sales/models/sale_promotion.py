from odoo import models, fields, api


class SalePromotion(models.Model):
    _name = 'sale.promotion'
    _inherit = ['pos.load.mixin']
    _description = 'Promotion commerciale'
    _order = 'date_start desc, name'

    name = fields.Char(
        string='Code promo',
        required=True,
        copy=False,
    )
    company_ids = fields.Many2many(
        'res.company',
        'sale_promotion_company_rel',
        'promotion_id',
        'company_id',
        string='Sociétés',
    )
    date_start = fields.Date(
        string='Date début',
        required=True,
    )
    date_end = fields.Date(
        string='Date fin',
        required=True,
    )
    line_ids = fields.One2many(
        'sale.promotion.line',
        'promotion_id',
        string='Lignes produits',
    )
    apply_in_pos = fields.Boolean(
        string='Appliquer en caisse (POS)',
        default=False,
        help="Si activé, la remise de cette promotion sera appliquée automatiquement "
             "en caisse sur les produits concernés pendant la période de validité.",
    )
    active = fields.Boolean(default=True)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise models.ValidationError(
                    "La date de fin doit être postérieure à la date de début."
                )

    @api.onchange('date_start', 'date_end')
    def _onchange_dates(self):
        """Propagate header dates to lines that still have the old header dates."""
        for line in self.line_ids:
            if not line.date_start or line.date_start == self._origin.date_start:
                line.date_start = self.date_start
            if not line.date_end or line.date_end == self._origin.date_end:
                line.date_end = self.date_end

    # ─── POS data loading ───────────────────────────────────────────────────────

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [('apply_in_pos', '=', True), ('active', '=', True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'date_start', 'date_end', 'line_ids', 'apply_in_pos']


class SalePromotionLine(models.Model):
    _name = 'sale.promotion.line'
    _inherit = ['pos.load.mixin']
    _description = 'Ligne de promotion'
    _order = 'promotion_id, sequence'

    promotion_id = fields.Many2one(
        'sale.promotion',
        string='Promotion',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product',
        string='Produit',
        required=True,
        domain=[('sale_ok', '=', True)],
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        related='product_id.product_tmpl_id',
        store=True,
        string='Modèle produit',
    )
    discount = fields.Float(
        string='Remise (%)',
        digits=(5, 2),
        required=True,
        default=0.0,
    )
    date_start = fields.Date(
        string='Date début',
        required=True,
    )
    date_end = fields.Date(
        string='Date fin',
        required=True,
    )

    @api.onchange('promotion_id')
    def _onchange_promotion_id(self):
        if self.promotion_id:
            self.date_start = self.promotion_id.date_start
            self.date_end = self.promotion_id.date_end

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise models.ValidationError(
                    "La date de fin doit être postérieure à la date de début sur la ligne %s."
                    % rec.product_id.display_name
                )

    @api.constrains('discount')
    def _check_discount(self):
        for rec in self:
            if rec.discount < 0 or rec.discount > 100:
                raise models.ValidationError(
                    "La remise doit être comprise entre 0 et 100 %% (ligne : %s)."
                    % rec.product_id.display_name
                )

    # ─── POS data loading ───────────────────────────────────────────────────────

    @api.model
    def _load_pos_data_domain(self, data, config):
        """Charge uniquement les lignes des promotions actives avec apply_in_pos."""
        active_promo_ids = self.env['sale.promotion'].search([
            ('apply_in_pos', '=', True),
            ('active', '=', True),
        ]).ids
        return [('promotion_id', 'in', active_promo_ids)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'promotion_id', 'product_id', 'discount', 'date_start', 'date_end']
