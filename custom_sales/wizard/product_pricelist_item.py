# -*- coding: utf-8 -*-
#############################################################################
#
#    Partenaire Succes Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Partenaire Succes(<https://www.partenairesucces.com>)
#    Author: Adama KONE
#
#############################################################################
from odoo import models, fields, _, api
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class ProductSelectWizard(models.TransientModel):
    _name = 'product.pricelist.item.wizard'
    _description = 'Sélection multiple de produits'


    def _default_pricelist_id(self):
        return self.id

    pricelist_id = fields.Many2one(
        comodel_name='product.pricelist',
        string="Pricelist",
        index=True, ondelete='cascade',
        required=True,
        default=_default_pricelist_id)
    
    products_tmpl_ids = fields.Many2many('product.template', string="Produits",
        help="Spécifiez les produits concernés par cette règle."
    )

    category_ids = fields.Many2many('product.category', string="Categories",
        help="Spécifiez les categories concernés par cette règle."
    )

    date_start = fields.Datetime(
        string="Start Date",
        help="Starting datetime for the pricelist item validation\n"
            "The displayed value depends on the timezone set in your preferences.")
    
    date_end = fields.Datetime(
        string="End Date",
        help="Ending datetime for the pricelist item validation\n"
            "The displayed value depends on the timezone set in your preferences.")
    
    min_quantity = fields.Float(
        string="Min. Quantity",
        default=0,
        digits='Product Unit of Measure',
        help="For the rule to apply, bought/sold quantity must be greater "
             "than or equal to the minimum quantity specified in this field.\n"
             "Expressed in the default unit of measure of the product.")
    
    display_applied_on = fields.Selection(
        selection=[
            ('1_product', "Produit"),
            ('2_product_category', "Categorie"),
        ],
        default='1_product',
        required=True,
        help="Pricelist Item applicable on selected option")
    
    price = fields.Char(
        string="Price",
        help="Explicit rule name for this pricelist line.")
    
    company_id = fields.Many2one(related='pricelist_id.company_id', store=True)
    currency_id = fields.Many2one(related='pricelist_id.currency_id', store=True)

    def action_add_products(self):
        active_id = self.env.context.get('active_id')
        pricelist_id = self.env['product.pricelist'].browse(active_id)
        if self.display_applied_on == '1_product':
            for product in self.products_tmpl_ids:
                self.env['product.pricelist.item'].create({
                    'pricelist_id': pricelist_id.id,
                    'product_tmpl_id' : product.id,
                    'name' : product.display_name,
                    'date_start' : self.date_start,
                    'date_end' : self.date_end,
                    'fixed_price': self.price,
                    'compute_price' : 'fixed',
                    'min_quantity': self.min_quantity,
                    'display_applied_on': '1_product',
                })
        elif self.display_applied_on == '2_product_category':
            for category in self.category_ids:
                self.env['product.pricelist.item'].create({
                    'pricelist_id': pricelist_id.id,
                    'categ_id' : category.id,
                    'name' : ("Category: %s", category.display_name),
                    'date_start' : self.date_start,
                    'date_end' : self.date_end,
                    'fixed_price': self.price,
                    'compute_price' : 'fixed',
                    'min_quantity': self.min_quantity,
                    'display_applied_on': '2_product_category',
                })