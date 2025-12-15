# -*- coding: utf-8 -*-
from odoo import api, fields, models
import re
from odoo.osv import expression

class ProductProduct(models.Model):
    """Inherits Products for multiple barcodes"""
    _inherit = 'product.product'

    multi_barcode_ids = fields.One2many(
        comodel_name='product.multiple.barcodes',
        inverse_name='product_id',
        string='Code-barres multiples',
    )

    def _check_multi_barcode(self, domain):
        """Check product have multi barcode or not"""
        product_id = None
        if len(domain) > 1:
            if 'barcode' in domain[0]:
                barcode = domain[0][2]
                bi_line = self.env['product.multiple.barcodes'].search(
                    [('product_multi_barcode', '=', barcode)])
                if bi_line:
                    product_id = bi_line.product_id.id
        return product_id


    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None,
                    order=None, load=True):
        """For searching the product with multi barcode"""
        product_id = self._check_multi_barcode(domain)
        if product_id:
            domain = [('id', '=', product_id)]
        res = super().search_read(
            domain=domain,
            fields=fields,
            offset=offset,
            limit=limit,
            order=order,
            load=load,  # 👈 très important
        )
        return res

    def _load_pos_data(self, data):
        """
        Charger les produits avec leurs codes-barres multiples pour le POS
        """
        res = super()._load_pos_data(data)

        if not res or not isinstance(res, list):
            return res

        product_barcodes = self.env['product.multiple.barcodes']

        for product in res:
            if isinstance(product, dict) and 'id' in product:
                secondary_barcodes = product_barcodes.search([
                    ('product_id', '=', product['id'])
                ]).mapped('product_multi_barcode')
                product['secondary_barcodes'] = secondary_barcodes or []

        return res

    @api.model_create_multi
    def create(self, vals):
        """Creating multi barcodes"""
        res = super(ProductProduct, self).create(vals)
        res.multi_barcode_ids.update({
            'product_template_id': res.product_tmpl_id.id
        })
        return res

    def write(self, vals):
        """Updating multi barcodes"""
        res = super(ProductProduct, self).write(vals)
        self.multi_barcode_ids.update({
            'product_template_id': self.product_tmpl_id.id
        })
        return res


    @api.model
    def _search_display_name(self, operator, value):
        is_positive = operator not in expression.NEGATIVE_TERM_OPERATORS
        combine = expression.OR if is_positive else expression.AND
        domains = [
            [('name', operator, value)],
            [('default_code', operator, value)],
            [('multi_barcode_ids', operator, value)],
            [('barcode', operator, value)],
            [('code_article', operator, value)],  # 👈 ajouté ici
        ]
        if operator in ('=', 'in') or (operator.endswith('like') and is_positive):
            barcode_values = [value] if operator != 'in' else value
            domains.append([('barcode', 'in', barcode_values)])
        if operator == '=' and isinstance(value, str) and (m := re.search(r'(\[(.*?)\])', value)):
            domains.append([('default_code', '=', m.group(2))])
        if partner_id := self.env.context.get('partner_id'):
            supplier_domain = [
                ('partner_id', '=', partner_id),
                '|',
                ('product_code', operator, value),
                ('product_name', operator, value),
            ]
            domains.append([('product_tmpl_id.seller_ids', 'any', supplier_domain)])

        return combine(domains)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not name:
            return super().name_search(name, args, operator, limit)

        positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
        is_positive = operator not in expression.NEGATIVE_TERM_OPERATORS
        products = self.browse()
        domain = args or []

        if operator in positive_operators:
            products = self.search_fetch(expression.AND([domain, [('default_code', '=', name)]]), ['display_name'],
                                         limit=limit) \
                       or self.search_fetch(expression.AND([domain, [('barcode', '=', name)]]), ['display_name'],
                                            limit=limit) \
                       or self.search_fetch(expression.AND([domain, [('code_article', '=', name)]]), ['display_name'],
                                            limit=limit)  # 👈 ajout

        if not products:
            if is_positive:
                products = self.search_fetch(expression.AND([domain, [('default_code', operator, name)]]),
                                             ['display_name'], limit=limit)
                limit_rest = limit and limit - len(products)
                if limit_rest is None or limit_rest > 0:
                    products |= self.search_fetch(
                        expression.AND([domain, [('id', 'not in', products.ids)], [('name', operator, name)]]),
                        ['display_name'], limit=limit_rest
                    )
                # 👇 recherche sur code_article si rien trouvé
                limit_rest = limit and limit - len(products)
                if limit_rest is None or limit_rest > 0:
                    products |= self.search_fetch(
                        expression.AND([domain, [('id', 'not in', products.ids)], [('code_article', operator, name)]]),
                        ['display_name'], limit=limit_rest
                    )
            else:
                domain_neg = [
                    ('name', operator, name),
                    '|', ('default_code', operator, name), ('default_code', '=', False),
                ]
                products = self.search_fetch(expression.AND([domain, domain_neg]), ['display_name'], limit=limit)

        if not products and operator in positive_operators and (m := re.search(r'(\[(.*?)\])', name)):
            match_domain = [('default_code', '=', m.group(2))]
            products = self.search_fetch(expression.AND([domain, match_domain]), ['display_name'], limit=limit)

        if not products and (partner_id := self.env.context.get('partner_id')):
            supplier_domain = [
                ('partner_id', '=', partner_id),
                '|',
                ('product_code', operator, name),
                ('product_name', operator, name),
            ]
            match_domain = [('product_tmpl_id.seller_ids', 'any', supplier_domain)]
            products = self.search_fetch(expression.AND([domain, match_domain]), ['display_name'], limit=limit)

        if not products:
            products = self.search_fetch(expression.AND([domain, [('multi_barcode_ids', operator, name)]]),
                                         ['display_name'], limit=limit)

        return [(product.id, product.display_name) for product in products.sudo()]
