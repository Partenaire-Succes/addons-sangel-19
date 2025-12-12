from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import re
import logging
import inspect

_logger = logging.getLogger(__name__)


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    code = fields.Char(
        string="Code",
        required=False,
        copy=False,
        readonly=False,
        default=False
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "Le code-barres doit être unique !")
    ]

    @api.model_create_multi
    def create(self, vals_list):
        import inspect

        # Analyser la pile d'appels pour détecter POS/Sale
        stack = inspect.stack()
        for frame in stack[:15]:
            filename = frame.filename.lower() if frame.filename else ""
            function_name = frame.function or ""

            # Bloquer si vient de modules POS ou Sale
            if any(module in filename for module in ['point_of_sale', 'pos_', 'sale_loyalty']):
                return self.browse()

            # Bloquer si fonction automatique détectée
            if any(func in function_name for func in ['_auto_create', 'generate_loyalty', 'create_loyalty']):
                _logger.info("Création automatique bloquée: %s", function_name)
                return self.browse()

        records = super().create(vals_list)

        for rec in records:
            if rec.code:
                rec.partner_id.customer_id = rec.code

        return records


    def write(self, vals):
        res = super().write(vals)
        for card in self:
            if card.code and card.partner_id:
                card.partner_id.customer_id = card.code
        return res
