from odoo import models, fields


class PosSession(models.Model):
    _inherit = 'pos.session'

    sage_x3_sent = fields.Boolean(string="Envoyé à SAGE X3", default=False, copy=False)
    sage_x3_sent_date = fields.Datetime(string="Date d'envoi à SAGE X3", copy=False)
    sage_x3_piece_number = fields.Char(string="Numéro de pièce SAGE X3", copy=False)
    message = fields.Text(
        string="Réponse SAGE X3",
        copy=False
    )

class PosPayment(models.Model):
    _inherit = 'pos.payment'

    sage_x3_sent = fields.Boolean(string="Envoyé à SAGE X3", default=False, copy=False)
    sage_x3_sent_date = fields.Datetime(string="Date d'envoi à SAGE X3", copy=False)
    sage_x3_piece_number = fields.Char(string="Numéro de pièce SAGE X3", copy=False)
    message = fields.Text(
        string="Réponse SAGE X3",
        copy=False
    )
