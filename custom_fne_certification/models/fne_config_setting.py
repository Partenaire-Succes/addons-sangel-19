import uuid

import odoo
from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError
import requests


import logging as logger
_logger = logger.getLogger(__name__)

DEFAULT_ENDPOINT = "http://54.247.95.108/ws/external/invoices/sign"


class FneConfigSettings(models.TransientModel):
    _name = 'fne.config.settings'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Paramètres de connexion FNE'
    _rec_name = 'fne_point_of_sale'

    is_fne = fields.Boolean(
        string="Certifiée FNE", default=False)
    fne_api_token = fields.Char(
        string='Token API FNE',
        store=True,
        help="Clé API fournie par la FNE pour authentifier les requêtes."
    )
    fne_point_of_sale = fields.Char(
        string='Point de vente',
        store=True,
        help="Point de vente fourni par la FNE.",
    )
    fne_establishment = fields.Char(
        string='Etablissement',
        store=True,
        help="Etablissement fourni par la FNE.",
    )
    state = fields.Selection([
        ('draft', 'Nouveau'),
        ('non_validated', 'Non validé'),
        ('validated', 'Validé'),
    ], string='Statut', default='draft', tracking=True)
    footer = fields.Char(
        string="Pied de page",
        help="Texte à afficher en pied de page des factures certifiées FNE."
    )

    def test_fne_connection(self):
        self.ensure_one()
        return True
        
        
    # def create(self, vals):
    #     if self.search_count([]) >= 1:
    #         raise ValidationError("Une seule configuration FNE est autorisée.")
    #     return super(FneConfigSettings, self).create(vals)