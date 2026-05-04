# -*- coding: utf-8 -*-
from odoo import fields, models


class StockReturnPickingLineCustom(models.TransientModel):
    _inherit = 'stock.return.picking.line'

    price_unit = fields.Float(
        string="Prix unitaire",
        digits='Product Price',
        default=0.0,
    )

    def _prepare_move_default_values(self, new_picking):
        vals = super()._prepare_move_default_values(new_picking)
        vals['price_unit'] = self.price_unit
        return vals

    def _process_line(self, new_picking):
        """Surcharge : après création du move retour, force le price_unit
        même si copy=False l'a remis à zéro."""
        result = super()._process_line(new_picking)
        if result and self.price_unit:
            return_move = new_picking.move_ids.filtered(
                lambda m: m.origin_returned_move_id == self.move_id
                          and m.product_id == self.product_id
            )
            if return_move:
                return_move[-1:].write({'price_unit': self.price_unit})
        return result


class StockReturnPickingCustom(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move):
        """Ajoute le prix unitaire du move d'origine dans les valeurs
        de la ligne de retour."""
        vals = super()._prepare_stock_return_picking_line_vals_from_move(stock_move)
        vals['price_unit'] = stock_move.price_unit
        return vals
