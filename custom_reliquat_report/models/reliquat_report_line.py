from odoo import models, fields, api


class ReliquatReportLine(models.Model):
    _name = 'reliquat.report.line'
    _description = 'Ligne de rapport de non livrés'

    report_id = fields.Many2one(
        comodel_name='reliquat.report',
        string='Rapport',
        required=True,
        ondelete='cascade'
    )

    purchase_order_id = fields.Many2one(
        comodel_name='purchase.order',
        string='Commande d\'achat'
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Fournisseur'
    )

    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Produits',
        required=True
    )

    qty_ordered = fields.Float(
        string='Quantité commandée',
        digits='Product Unit of Measure'
    )

    qty_received = fields.Float(
        string='Quantité reçue',
        digits='Product Unit of Measure'
    )

    qty_pending = fields.Float(
        string='Quantité en attente',
        digits='Product Unit of Measure'
    )

    satisfaction_rate = fields.Float(string='Taux de satisfaction')

    order_date = fields.Date(string='Date de commande')

    product_name = fields.Char(
        related='product_id.name',
        string='Produits'
    )

    partner_name = fields.Char(
        related='partner_id.name',
        string='Fournisseurs'
    )

