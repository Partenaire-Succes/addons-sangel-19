from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    date_importation = fields.Datetime(
        string="Date d'importation",
        copy=False,
        help="Date provenant du fichier d'importation. Utilisez le bouton pour l'appliquer comme date du devis.",
    )

    def action_apply_import_date(self):
        sale_order = self.env['sale.order'].search([('date_importation', '!=', False)])
        for so in sale_order:
<<<<<<< HEAD
            if so.state != 'sale':
                so.action_confirm()
                so.date_order = so.date_importation
                
=======
            so.action_confirm()
            so.date_order = so.date_importation
>>>>>>> marcel_dev
