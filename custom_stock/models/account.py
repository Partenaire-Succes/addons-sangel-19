import logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime

_logger = logging.getLogger(__name__)



class AccountMoveSageX3(models.Model):
    _inherit = "account.move"

    # Champs de suivi SAGE X3
    sage_x3_sent = fields.Boolean(
        string="Envoyé à SAGE X3",
        default=False,
        copy=False,
        help="Indique si la facture a été envoyée à SAGE X3"
    )
    sage_x3_sent_date = fields.Datetime(
        string="Date envoi SAGE X3",
        copy=False
    )
    sage_sent = fields.Boolean(
        string="Doit etre envoyé",
        default=False,
        copy=False
    )
    sage_x3_piece = fields.Char(string="Type pièce SAGE X3", readonly=True, copy=False)
    sage_x3_piece_type = fields.Selection([
        ('FACLI', 'Facture client'),
        ('REGCLI', 'Règlement client'),
    ], string="Type pièce SAGE X3", readonly=True, copy=False)
    sage_x3_piece_number = fields.Char(
        string="N° Pièce SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_response = fields.Text(
        string="Réponse SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_error = fields.Text(
        string="Erreur SAGE X3",
        readonly=True,
        copy=False
    )
    message = fields.Text(
        string="Message",
        copy=False
    )


class AccountPaymentSageX3(models.Model):
    _inherit = "account.payment"

    sage_x3_sent = fields.Boolean(
        string="Envoyé à SAGE X3",
        default=False,
        copy=False
    )
    sage_x3_sent_date = fields.Datetime(
        string="Date envoi SAGE X3",
        copy=False
    )
    sage_x3_piece_number = fields.Char(
        string="N° Pièce SAGE X3",
        readonly=True,
        copy=False
    )
    sage_x3_error = fields.Text(
        string="Erreur SAGE X3",
        readonly=True,
        copy=False
    )
    num_costomer_bank = fields.Char(
        string="Numéro de compte bancaire client",
        copy=False
    )
    message = fields.Text(
        string="Message",
        copy=False
    )