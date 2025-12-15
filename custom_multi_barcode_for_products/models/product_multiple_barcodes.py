# -*- coding: utf-8 -*-
from odoo import fields, models, api,_
from odoo.exceptions import ValidationError


class ProductMultiBarcode(models.Model):
    """Creating multiple barcode for products"""
    _name = 'product.multiple.barcodes'
    _description = 'Product Multiple Barcodes'
    _rec_name = 'product_multi_barcode'

    product_multi_barcode = fields.Char(
        string="Barcode",
    )

    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Variante de produit",
    )

    product_template_id = fields.Many2one(
        comodel_name='product.template',
        string="Produit"
    )

    _sql_constraints = [
        ('field_unique', 'unique(product_multi_barcode)',
         'Existing barcode is not allowed !'),]

    is_active_barcode = fields.Boolean(
        string="Est principal",
        default=False,
    )

    @api.constrains('is_active_barcode', 'product_template_id')
    def _check_unique_active_barcode(self):
        """Un seul code-barres actif par produit"""
        for record in self:
            if record.is_active_barcode and record.product_template_id:
                other_active = self.search([
                    ('product_template_id', '=', record.product_template_id.id),
                    ('is_active_barcode', '=', True),
                    ('id', '!=', record.id)
                ])
                if other_active:
                    raise ValidationError(_(
                        "Un seul code-barres peut être actif par produit."
                    ))

    def _sync_barcode_to_product(self, barcode_value, product_id):
        """Synchronise le code-barres avec product.product"""
        if barcode_value:
            self.env.cr.execute("""
                    UPDATE product_product 
                    SET barcode = %s 
                    WHERE id = %s
                """, (barcode_value, product_id))
        else:
            self.env.cr.execute("""
                    UPDATE product_product 
                    SET barcode = NULL 
                    WHERE id = %s
                """, (product_id,))
        self.env['product.product'].browse(product_id).invalidate_recordset(['barcode'])

    def write(self, vals):
        """Synchronise le code-barres actif avec product.product"""
        # Désactiver les autres si on active celui-ci
        if vals.get('is_active_barcode'):
            for record in self:
                if record.product_id:
                    other_active = self.search([
                        ('product_id', '=', record.product_id.id),
                        ('is_active_barcode', '=', True),
                        ('id', '!=', record.id)
                    ])
                    if other_active:
                        other_active.write({'is_active_barcode': False})

                elif record.product_template_id:
                    other_active = self.search([
                        ('product_template_id', '=', record.product_template_id.id),
                        ('is_active_barcode', '=', True),
                        ('id', '!=', record.id)
                    ])
                    if other_active:
                        other_active.write({'is_active_barcode': False})

        res = super(ProductMultiBarcode, self).write(vals)

        for record in self:
            # Synchroniser avec product.product (variante)
            if record.product_id:
                if record.is_active_barcode:
                    self._sync_barcode_to_product(record.product_multi_barcode, record.product_id.id)
                elif record.product_id.barcode == record.product_multi_barcode:
                    # Vérifier s'il y a un autre code-barres actif
                    other_active = self.search([
                        ('product_id', '=', record.product_id.id),
                        ('is_active_barcode', '=', True),
                        ('id', '!=', record.id)
                    ], limit=1)
                    if other_active:
                        self._sync_barcode_to_product(other_active.product_multi_barcode, record.product_id.id)
                    else:
                        self._sync_barcode_to_product(False, record.product_id.id)

            # Synchroniser avec toutes les variantes du template
            elif record.product_template_id:
                variants = record.product_template_id.product_variant_ids
                for variant in variants:
                    if record.is_active_barcode:
                        self._sync_barcode_to_product(record.product_multi_barcode, variant.id)
                    elif variant.barcode == record.product_multi_barcode:
                        other_active = self.search([
                            ('product_template_id', '=', record.product_template_id.id),
                            ('is_active_barcode', '=', True),
                            ('id', '!=', record.id)
                        ], limit=1)
                        if other_active:
                            self._sync_barcode_to_product(other_active.product_multi_barcode, variant.id)
                        else:
                            self._sync_barcode_to_product(False, variant.id)

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Synchronise le code-barres actif lors de la création"""
        records = super(ProductMultiBarcode, self).create(vals_list)

        for record in records:
            # Si aucun code-barres n'est marqué comme actif, activer celui-ci
            should_activate = False

            if record.product_id:
                active_exists = self.search_count([
                    ('product_id', '=', record.product_id.id),
                    ('is_active_barcode', '=', True)
                ])
                if not active_exists:
                    should_activate = True

            elif record.product_template_id:
                active_exists = self.search_count([
                    ('product_template_id', '=', record.product_template_id.id),
                    ('is_active_barcode', '=', True)
                ])
                if not active_exists:
                    should_activate = True

            # Activer ce code-barres s'il n'y en a pas d'autre actif
            if should_activate and not record.is_active_barcode:
                record.is_active_barcode = True

            # Synchroniser si actif
            if record.is_active_barcode:
                if record.product_id:
                    self._sync_barcode_to_product(record.product_multi_barcode, record.product_id.id)

                elif record.product_template_id:
                    variants = record.product_template_id.product_variant_ids
                    for variant in variants:
                        self._sync_barcode_to_product(record.product_multi_barcode, variant.id)

        return records

    def unlink(self):
        """Vide le code-barres si on supprime le code-barres actif"""
        for record in self:
            if record.is_active_barcode:
                # Nettoyer product.product (variante)
                if record.product_id:
                    # Chercher le dernier code-barres restant
                    last_barcode = self.search([
                        ('product_id', '=', record.product_id.id),
                        ('id', '!=', record.id)
                    ], order='id desc', limit=1)

                    if last_barcode:
                        # Activer le dernier code-barres
                        last_barcode.is_active_barcode = True
                    else:
                        # Aucun autre code-barres, vider
                        self._sync_barcode_to_product(False, record.product_id.id)

                # Nettoyer toutes les variantes du template
                elif record.product_template_id:
                    # Chercher le dernier code-barres restant
                    last_barcode = self.search([
                        ('product_template_id', '=', record.product_template_id.id),
                        ('id', '!=', record.id)
                    ], order='id desc', limit=1)

                    variants = record.product_template_id.product_variant_ids
                    if last_barcode:
                        # Activer le dernier code-barres
                        last_barcode.is_active_barcode = True
                    else:
                        # Aucun autre code-barres, vider
                        for variant in variants:
                            self._sync_barcode_to_product(False, variant.id)

        return super(ProductMultiBarcode, self).unlink()

    def get_barcode_val(self, product):
        """
        Summary:
            get barcode of record in self and product id
        Args:
            product(int):current product
        Returns:
            barcode of the record in self and product
        """

        return self.product_multi_barcode, product

    # @api.model
    # def create(self, vals_list):
    #     records = super().create(vals_list)
    #     for record, vals in zip(records, vals_list if isinstance(vals_list, list) else [vals_list]):
    #         if vals.get('product_multi_barcode'):
    #             record.product_id.barcode = vals['product_multi_barcode']
    #             record.product_template_id.barcode = vals['product_multi_barcode']
    #     return records

