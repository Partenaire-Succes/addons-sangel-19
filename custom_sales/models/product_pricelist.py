from odoo import models, fields, api, _
from odoo.exceptions import AccessError


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    allowed_company_ids = fields.Many2many(
        'res.company',
        'pricelist_allowed_company_rel',  # table relation
        'pricelist_id',  # colonne côté pricelist
        'company_id',  # colonne côté company
        string="Sociétés"
    )


    def action_open_wizard(self):
        return {
            'name': "Ajouter produits",
            'type': 'ir.actions.act_window',
            'res_model': 'product.pricelist.item.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_pricelist_id': self.id,
            }
        }

    @api.model
    def search(self, args, **kwargs):
        """Filtrage automatique pour ne pas afficher les listes non autorisées."""
        if self._name == "product.pricelist" and not self.env.su:
            user_companies = self.env.companies.ids
            args = [
                       '|',
                       ('allowed_company_ids', '=', False),
                       ('allowed_company_ids', 'in', user_companies)
                   ] + list(args)
        return super(ProductPricelist, self).search(args, **kwargs)
