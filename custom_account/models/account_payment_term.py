import logging
import re
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountPaymentTermInherit(models.Model):
    _inherit = 'account.payment.term'


    payment_method = fields.Selection([
            ('chq', 'Chèque'), 
            ('esp', 'Especes'),
            ('vir', 'Virement'),
        ], string='Mode de reglement', 
            default='esp', 
            required=True
    )
    