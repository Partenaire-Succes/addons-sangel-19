from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_promo_3x4 = fields.Boolean(string="Promo 3=4")
    is_promo = fields.Boolean('Promo 3+1', default=False)
    
