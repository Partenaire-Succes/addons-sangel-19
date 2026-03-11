from odoo import models, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_pricelist_for_company(self, company=None):
        """Retourne la liste de prix applicable pour ce partenaire dans une société donnée."""
        self.ensure_one()
        company = company or self.env.company

        # 1) Si la liste de prix assignée est valide pour la société
        if self.property_product_pricelist:
            pl = self.property_product_pricelist
            if not pl.allowed_company_ids or company in pl.allowed_company_ids:
                return pl

        # 2) Sinon, on cherche une liste de prix globale ou autorisée pour cette société
        return self.env['product.pricelist'].search([
            '|',
            ('allowed_company_ids', 'in', company.id),
            ('allowed_company_ids', '=', False)
        ], limit=1)
