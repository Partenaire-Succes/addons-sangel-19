from email.policy import default

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import re


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    customer_id = fields.Char(
        string="ID client",
        copy=False,
        tracking=True
    )

    discount_eligible = fields.Boolean(
        string="Éligible à la remise",
        default=False,
        help="Cochez si ce client peut bénéficier d'une remise.",
        tracking = True
    )

    discount_percentage = fields.Float(
        string="Pourcentage de remise",
        default=0.0,
        help="Entrez le pourcentage de remise que ce client bénéficiera.",
        tracking=True
    )

    is_airsi_eligible = fields.Boolean(
        string="Éligible à l'AIRSI",
        default=False,
        help="Cochez si ce client est assujetti à l'AIRSI.",
        tracking = True
    )

    code_family = fields.Char(
        string="Code famille",
        tracking = True
    )

    secondary_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable secondaire",
        tracking = True
    )

    primary_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsable principal",
        tracking = True
    )

    create_date_sage = fields.Datetime(string="Date création SAGE")

    update_date_sage = fields.Datetime(string="Date MAJ SAGE")

    discount_start_date = fields.Date(
        string="Date de début remise",
        help="La remise est applicable uniquement à partir de cette date.",
        tracking = True
    )

    discount_end_date = fields.Date(
        string="Date de fin remise",
        help="La remise cesse d’être applicable après cette date.",
        tracking = True
    )

    _sql_constraints = [
        ('customer_id_unique', 'unique(customer_id)', 'Le ID client doit être unique !')
    ]

    loyalty_card_ids = fields.One2many(
        comodel_name="loyalty.card",
        inverse_name="partner_id",
        string="Cartes de fidélité"
    )

    @api.onchange('discount_eligible')
    def onchange_discount_start_date(self):
        for rec in self:
            if rec.discount_eligible:
                rec.discount_start_date = fields.Date.today()
            else:
                rec.discount_start_date = False
