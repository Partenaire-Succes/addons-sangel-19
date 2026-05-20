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

    @api.depends('line_ids', 'supplier_id')
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
            # if qty_to_order == 0:
            #     continue
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

        lang = self.supplier_id.lang or self.env.lang
        for line in lines:
            product = line.product_id
            product_lang = product.with_context(lang=lang)
            name = product_lang.display_name or product.name or '/'
            if product_lang.description_purchase:
                name += '\n' + product_lang.description_purchase

            taxes = product.supplier_taxes_id.filtered(
                lambda t: t.company_id.id == self.company_id.id
            )

            self.env['purchase.order.line'].create({
                'order_id': po.id,
                'product_id': product.id,
                'name': name,
                'product_qty': line.qty_to_order,
                'product_uom_id': line.product_uom_id.id,
                'price_unit': line.price_unit,
                'date_planned': fields.Datetime.now(),
                'tax_ids': [(6, 0, taxes.ids)],
                'orderpoint_id': line.orderpoint_id.id,
            })

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
