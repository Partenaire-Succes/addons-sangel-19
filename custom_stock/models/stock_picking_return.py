# -*- coding: utf-8 -*-
from odoo import fields, models


class StockReturnPickingLineCustom(models.TransientModel):
    """
    Hérite stock.return.picking.line pour ajouter le prix unitaire.
    Le prix est repris depuis le stock.move d'origine et retransmis
    au nouveau move créé lors du retour.
    """
    _inherit = 'stock.return.picking.line'

    price_unit = fields.Float(
        string="Prix unitaire",
        digits='Product Price',
        default=0.0,
    )

    def _prepare_move_default_values(self, new_picking):
        """
        Surcharge : injecte le prix unitaire dans les valeurs du move retour.
        Le champ price_unit existe sur stock.move (utilisé pour valorisation).
        """
        vals = super()._prepare_move_default_values(new_picking)
        vals['price_unit'] = self.price_unit
        return vals


class StockReturnPickingCustom(models.TransientModel):
    """
    Hérite stock.return.picking pour alimenter le price_unit
    sur chaque ligne de retour depuis le move d'origine.
    """
    _inherit = 'stock.return.picking'

    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move):
        """
        Surcharge : ajoute le prix unitaire du move d'origine
        dans les valeurs de la ligne de retour.

        Odoo remplit stock.move.price_unit depuis :
          - la valorisation du mouvement (average cost, FIFO…)
          - ou le prix d'achat de la ligne de bon de commande (purchase.order.line)
        On prend directement stock_move.price_unit qui est toujours renseigné
        sur un move 'done'.
        """
        vals = super()._prepare_stock_return_picking_line_vals_from_move(stock_move)
        vals['price_unit'] = stock_move.price_unit
        return vals