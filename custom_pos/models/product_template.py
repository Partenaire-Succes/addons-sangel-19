# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    pricelist_rule_count = fields.Integer(
        string='Nombre de listes de prix',
        compute='_compute_pricelist_rule_count',
    )

    @api.depends('pricelist_rule_ids')
    def _compute_pricelist_rule_count(self):
        for product in self:
            product.pricelist_rule_count = len(product.pricelist_rule_ids)

    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        for f in ('airsi_taxes_id', 'percentage_airsi'):
            if f not in fields:
                fields.append(f)
        return fields

    def action_delete_pricelist_rules(self):
        products = self.env['product.template'].search([])
        for product in products:
            product.pricelist_rule_ids.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Listes de prix supprimées"),
                'message': _("Toutes les listes de prix du produit ont été supprimées."),
                'type': 'success',
                'sticky': False,
            },
        }
