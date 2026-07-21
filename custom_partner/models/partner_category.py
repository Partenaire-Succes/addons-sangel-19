from odoo import fields, models, api


class ResPartnerCategory(models.Model):
    _inherit = 'res.partner.category'

    code = fields.Char(string="Code", index=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "Le code de catégorie doit être unique."),
    ]
