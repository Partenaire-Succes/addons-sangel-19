# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    label_logo = fields.Binary(
        string='Logo étiquette produit',
        attachment=True,
        help="Logo affiché sur les étiquettes produits (format recommandé : PNG carré, fond blanc)."
    )
