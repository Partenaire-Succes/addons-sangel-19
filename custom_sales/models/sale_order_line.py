from odoo import models, fields, api
from datetime import date


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.onchange('product_id', 'product_uom_qty', 'price_unit')
    def _onchange_product_id(self):
        """Déclenché lors des changements dans l'interface utilisateur"""
        self._apply_discount_from_rules()

    def _apply_discount_from_rules(self):
        """Applique la remise automatiquement selon produit et client."""
        today = fields.Date.context_today(self)
        for line in self:
            product = line.product_id.product_tmpl_id
            partner = line.order_id.partner_id
            order_date = line.order_id.date_order.date() if line.order_id.date_order else today

            if (
                    product and product.discount_ligne
                    and partner.discount_eligible
                    and partner.discount_percentage > 0
                    and (not partner.discount_start_date or partner.discount_start_date <= order_date)
                    and (not partner.discount_end_date or partner.discount_end_date >= order_date)
            ):
                # new_discount = partner.discount_percentage * 100
                line.discount = partner.discount_percentage * 100
            else:
                pass
                # new_discount = 0.0

            # Éviter la récursion : ne pas déclencher write() si la valeur n'a pas changé
            # if line.discount != new_discount:
            #     # Utiliser with_context pour éviter les déclencheurs récursifs
            #     line.with_context(skip_discount_rules=True).discount = new_discount

    @api.model_create_multi
    def create(self, vals):
        """Surcharge de create pour appliquer les règles de remise"""
        res = super(SaleOrderLine, self).create(vals)
        # Appliquer les règles seulement si pas dans un contexte d'évitement
        if not self.env.context.get('skip_discount_rules'):
            res._apply_discount_from_rules()

        return res

    def write(self, vals):
        """Surcharge de write pour appliquer les règles de remise"""
        # Éviter la récursion si on est déjà dans le contexte d'application des règles
        if self.env.context.get('skip_discount_rules'):
            return super(SaleOrderLine, self).write(vals)

        res = super(SaleOrderLine, self).write(vals)
        # Appliquer les règles seulement sur les champs pertinents
        if any(field in vals for field in ['product_id', 'product_uom_qty', 'price_unit', 'order_id']):
            for line in self:
                line._apply_discount_from_rules()

        return res


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.onchange('partner_id', 'order_line')
    def _onchange_partner_id(self):
        """Déclenché lors du changement de partenaire dans l'interface"""
        # Utiliser filtered() pour éviter les erreurs sur les lignes vides
        for order_line in self.order_line.filtered('product_id'):
            order_line._apply_discount_from_rules()
