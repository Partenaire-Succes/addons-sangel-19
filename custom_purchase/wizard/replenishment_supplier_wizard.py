# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class ReplenishmentSupplierWizard(models.TransientModel):
    _name = 'replenishment.supplier.wizard'
    _description = 'Réassort par Fournisseur'

    supplier_id = fields.Many2one(
        'res.partner',
        string='Fournisseur',
        domain=[('supplier_rank', '>', 0)],
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        'replenishment.supplier.wizard.line',
        'wizard_id',
        string='Produits à commander',
    )
    line_count = fields.Integer(compute='_compute_line_count')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids.filtered(lambda l: l.qty_to_order > 0))

    @api.onchange('supplier_id')
    def _onchange_supplier_id(self):
        self.line_ids = [(5, 0, 0)]
        if not self.supplier_id:
            return

        orderpoints = self.env['stock.warehouse.orderpoint'].search([
            ('company_id', '=', self.env.company.id),
        ])

        lines = []
        for op in orderpoints:
            seller = op.product_id.seller_ids.filtered(
                lambda s: s.partner_id == self.supplier_id
            ) or op.product_id.product_tmpl_id.seller_ids.filtered(
                lambda s: s.partner_id == self.supplier_id
            )
            if not seller:
                continue

            qty_to_order = max(0.0, op.qty_to_order or 0.0)
            lines.append((0, 0, {
                'orderpoint_id': op.id,
                'product_id': op.product_id.id,
                'location_id': op.location_id.id,
                'qty_on_hand': op.qty_on_hand,
                'product_min_qty': op.product_min_qty,
                'product_max_qty': op.product_max_qty,
                'qty_to_order': qty_to_order,
                'price_unit': seller[0].price,
                'product_uom_id': op.product_uom.id,
            }))

        self.line_ids = lines

    def action_create_purchase_order(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.qty_to_order > 0)
        if not lines:
            raise UserError("Aucune quantité à commander. Vérifiez les quantités saisies.")

        po = self.env['purchase.order'].create({
            'partner_id': self.supplier_id.id,
            'company_id': self.company_id.id,
        })

        PurchaseLine = self.env['purchase.order.line']
        for line in lines:
            # Utiliser la méthode native d'Odoo qui construit correctement
            # name, date_planned, tax_ids, price_unit depuis le seller
            vals = PurchaseLine._prepare_purchase_order_line(
                product_id=line.product_id,
                product_qty=line.qty_to_order,
                product_uom=line.product_uom_id,
                company_id=self.company_id,
                partner_id=self.supplier_id,
                po=po,
            )
            # Garder le prix saisi dans le wizard
            vals['price_unit'] = line.price_unit
            PurchaseLine.create(vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }


class ReplenishmentSupplierWizardLine(models.TransientModel):
    _name = 'replenishment.supplier.wizard.line'
    _description = 'Ligne Réassort par Fournisseur'

    wizard_id = fields.Many2one('replenishment.supplier.wizard', ondelete='cascade')
    orderpoint_id = fields.Many2one('stock.warehouse.orderpoint', string='Règle')
    product_id = fields.Many2one('product.product', string='Produit')
    location_id = fields.Many2one('stock.location', string='Emplacement')
    qty_on_hand = fields.Float(string='Stock actuel')
    product_min_qty = fields.Float(string='Min')
    product_max_qty = fields.Float(string='Max')
    qty_to_order = fields.Float(string='Qté à commander')
    price_unit = fields.Float(string='Prix unitaire')
    product_uom_id = fields.Many2one('uom.uom', string='UdM')
    subtotal = fields.Float(string='Sous-total', compute='_compute_subtotal')

    @api.depends('qty_to_order', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty_to_order * line.price_unit
