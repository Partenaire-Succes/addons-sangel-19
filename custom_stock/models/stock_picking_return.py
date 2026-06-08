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


class StockReturnPickingCustom(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move):
        vals = super()._prepare_stock_return_picking_line_vals_from_move(stock_move)
        # Le prix unitaire du retour est obligatoire (cf. vue héritée) : si le
        # mouvement d'origine n'a pas de prix (price_unit = 0), on retombe sur
        # le coût actuel de l'article plutôt que d'afficher 0 — ainsi le champ
        # n'est jamais vide/à zéro à l'ouverture du wizard.
        vals['price_unit'] = stock_move.price_unit or stock_move.product_id.standard_price
        return vals

    def _create_return(self):
        new_picking = super()._create_return()
        # price_unit a copy=False sur stock.move et est susceptible d'être
        # remis à zéro par action_confirm() / _merge_moves().
        # On force la valeur sur les moves retour APRÈS que tout est confirmé.
        price_map = {
            line.move_id.id: line.price_unit
            for line in self.product_return_moves
            if line.move_id and line.price_unit
        }
        if price_map:
            for move in new_picking.move_ids:
                orig_id = move.origin_returned_move_id.id
                if orig_id in price_map:
                    move.price_unit = price_map[orig_id]
        return new_picking
