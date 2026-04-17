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
    date_start = fields.Date(string='Date début', required=True)
    date_end = fields.Date(string='Date fin', required=True)
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

    # ─── Remise (saisie) ────────────────────────────────────────────────────────

    discount = fields.Float(
        string='Remise (%)',
        digits=(5, 2),
        required=True,
        default=0.0,
        help="Pourcentage de remise. Peut aussi être calculé automatiquement "
             "si vous saisissez le Promo HT directement.",
    )

    # ─── Dates ──────────────────────────────────────────────────────────────────

    date_start = fields.Date(string='Date début')
    date_end = fields.Date(string='Date fin')

    # ─── Prix de vente courants (lecture seule, issus du produit) ──────────────

    price_ht = fields.Float(
        string='PV HT',
        compute='_compute_base_prices',
        digits='Product Price',
        help="Prix de vente hors taxe actuel du produit.",
    )
    price_ttc = fields.Float(
        string='PV TTC',
        compute='_compute_base_prices',
        digits='Product Price',
        help="Prix de vente toutes taxes comprises actuel du produit.",
    )
    ttc_tx = fields.Float(
        string='TTC+TX',
        compute='_compute_base_prices',
        digits='Product Price',
        help="Montant de la taxe sur le prix de vente normal (PV TTC − PV HT).",
    )

    # ─── Prix promo : PIVOT = promo_ht (editable OU calculé depuis remise) ──────
    #
    #   Deux modes de saisie possibles :
    #   1. L'utilisateur saisit la remise (%) → promo_ht se calcule
    #   2. L'utilisateur saisit directement promo_ht → la remise se calcule
    #
    # ────────────────────────────────────────────────────────────────────────────

    promo_ht = fields.Float(
        string='Promo HT',
        digits='Product Price',
        default=0.0,
        help="Prix de vente HT promo. Saisissez ce prix directement pour calculer "
             "la remise automatiquement, ou renseignez la remise (%) pour le calculer.",
    )

    # ─── Prix d'achat promo (saisi manuellement) ───────────────────────────────

    promo_pa = fields.Float(
        string='Promo PA',
        digits='Product Price',
        default=0.0,
        help="Prix d'achat promotionnel négocié avec le fournisseur.",
    )

    # ─── Calculés depuis promo_ht + taxes ──────────────────────────────────────

    promo_ttc = fields.Float(
        string='Promo TTC',
        compute='_compute_promo_prices',
        digits='Product Price',
        help="Prix de vente TTC après remise (calculé depuis Promo HT + taxes).",
    )
    ht_tx = fields.Float(
        string='HT+TX',
        compute='_compute_promo_prices',
        digits='Product Price',
        help="Montant de la taxe sur le prix promo (Promo TTC − Promo HT).",
    )

    # ─── Ratios commerciaux (calculés) ─────────────────────────────────────────

    coeff = fields.Float(
        string='Coeff Réf',
        compute='_compute_ratios',
        digits=(10, 4),
        help="Coefficient de référence = PV HT / Promo PA.",
    )
    promo_coeff = fields.Float(
        string='Promo Coeff',
        compute='_compute_ratios',
        digits=(10, 4),
        help="Coefficient promo = Promo HT / Promo PA.",
    )
    promo_tx_marque = fields.Float(
        string='Promo TX Marque',
        compute='_compute_ratios',
        digits=(10, 4),
        help="Taux de marque promo (%) = (Promo HT − Promo PA) / Promo HT × 100.",
    )

    # ─── Stock (lecture seule, temps réel) ─────────────────────────────────────

    qty_available = fields.Float(
        string='Stock dispo',
        compute='_compute_stock',
        digits='Product Unit of Measure',
        help="Quantité disponible en stock (en main).",
    )
    virtual_available = fields.Float(
        string='Stock virtuel',
        compute='_compute_stock',
        digits='Product Unit of Measure',
        help="Stock virtuel = stock disponible + réceptions en cours − sorties prévues.",
    )

    # ─── Méthodes de calcul ─────────────────────────────────────────────────────

    @api.depends('product_id', 'product_id.lst_price', 'product_id.taxes_id')
    @api.depends_context('company')
    def _compute_base_prices(self):
        """Prix de vente courants du produit (HT, TTC, montant taxe normal)."""
        for line in self:
            product = line.product_id
            if not product:
                line.price_ht = 0.0
                line.price_ttc = 0.0
                line.ttc_tx = 0.0
                continue

            base = product.lst_price
            taxes = product.taxes_id.filtered(
                lambda t: t.company_id == line.env.company
            )
            if taxes:
                res = taxes.compute_all(
                    base, product=product, partner=line.env['res.partner']
                )
                p_ht = res['total_excluded']
                p_ttc = res['total_included']
            else:
                p_ht = base
                p_ttc = base

            line.price_ht = p_ht
            line.price_ttc = p_ttc
            line.ttc_tx = p_ttc - p_ht

    @api.depends('promo_ht', 'product_id', 'product_id.taxes_id')
    @api.depends_context('company')
    def _compute_promo_prices(self):
        """Prix TTC promo et montant taxe sur prix promo."""
        for line in self:
            product = line.product_id
            p_promo_ht = line.promo_ht or 0.0

            if not product or not p_promo_ht:
                line.promo_ttc = p_promo_ht
                line.ht_tx = 0.0
                continue

            taxes = product.taxes_id.filtered(
                lambda t: t.company_id == line.env.company
            )
            if taxes:
                res = taxes.compute_all(
                    p_promo_ht, product=product, partner=line.env['res.partner']
                )
                p_promo_ttc = res['total_included']
            else:
                p_promo_ttc = p_promo_ht

            line.promo_ttc = p_promo_ttc
            line.ht_tx = p_promo_ttc - p_promo_ht

    @api.depends('price_ht', 'promo_ht', 'promo_pa')
    def _compute_ratios(self):
        """Ratios commerciaux : coeff, promo_coeff, taux de marque."""
        for line in self:
            p_ht = line.price_ht or 0.0
            promo_ht = line.promo_ht or 0.0
            promo_pa = line.promo_pa or 0.0

            line.coeff = p_ht / promo_pa if promo_pa else 0.0
            line.promo_coeff = promo_ht / promo_pa if promo_pa else 0.0
            line.promo_tx_marque = (
                (promo_ht - promo_pa) / promo_ht * 100.0
                if promo_ht else 0.0
            )

    @api.depends('product_id')
    def _compute_stock(self):
        """Stock disponible et stock virtuel (temps réel)."""
        for line in self:
            if line.product_id:
                line.qty_available = line.product_id.qty_available
                line.virtual_available = line.product_id.virtual_available
            else:
                line.qty_available = 0.0
                line.virtual_available = 0.0

    # ─── Onchanges bidirectionnels (remise ↔ promo_ht) ─────────────────────────

    @api.onchange('discount', 'product_id')
    def _onchange_discount(self):
        """Remise modifiée → recalcule Promo HT."""
        p_ht = self.price_ht
        if p_ht:
            self.promo_ht = round(
                p_ht * (1.0 - (self.discount or 0.0) / 100.0), 6
            )

    @api.onchange('promo_ht')
    def _onchange_promo_ht(self):
        """Promo HT saisi directement → recalcule la remise (%)."""
        p_ht = self.price_ht
        promo_ht = self.promo_ht or 0.0
        if p_ht and p_ht > 0:
            self.discount = round((1.0 - promo_ht / p_ht) * 100.0, 2)

    # ─── Onchange dates depuis l'entête ────────────────────────────────────────

    @api.onchange('promotion_id')
    def _onchange_promotion_id(self):
        if self.promotion_id:
            self.date_start = self.promotion_id.date_start
            self.date_end = self.promotion_id.date_end

    # ─── Contraintes ───────────────────────────────────────────────────────────

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
        active_promo_ids = self.env['sale.promotion'].search([
            ('apply_in_pos', '=', True),
            ('active', '=', True),
        ]).ids
        return [('promotion_id', 'in', active_promo_ids)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'promotion_id', 'product_id', 'discount', 'date_start', 'date_end']
