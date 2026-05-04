from odoo import fields, models, api, _
from odoo.exceptions import UserError


class PurchaseOrderLineCustom(models.Model):
    _inherit = 'purchase.order.line'

    @api.onchange('product_id')
    def _onchange_product_id_fill_standard_price(self):
        """Si le prix reste à 0 après le onchange natif, prendre le standard_price."""
        if self.product_id and not self.price_unit:
            std = self.product_id.standard_price
            if std:
                self.price_unit = std

    @api.model_create_multi
    def create(self, vals_list):
        # récupérer tous les produits en une seule requête
        product_ids = [vals.get('product_id') for vals in vals_list if vals.get('product_id')]
        products = self.env['product.product'].browse(product_ids)
        product_map = {p.id: p for p in products}

        for vals in vals_list:
            if vals.get('price_unit', 0) == 0:
                product = product_map.get(vals.get('product_id'))
                if product and product.standard_price:
                    vals['price_unit'] = product.standard_price

        return super().create(vals_list)


class PurchaseOrderSageX3Optimized(models.Model):
    _inherit = "purchase.order"

    sage_x3_submitted = fields.Boolean(string="Soumis à SAGE X3", default=False, readonly=True, copy=False)
    sage_x3_validated = fields.Boolean(string="Accepté par SAGE X3", default=False, readonly=True, copy=False)
    sage_x3_submitted_date = fields.Datetime(string="Date soumission SAGE X3", readonly=True, copy=False)
    sage_x3_response_message = fields.Text(string="Message SAGE X3", readonly=True, copy=False)
    sage_x3_error = fields.Text(string="Erreur SAGE X3", readonly=True, copy=False)
    sage_x3_delivery_received = fields.Boolean(string="Livraison reçue", default=False, readonly=True)
    sage_x3_delivery_date = fields.Datetime(string="Date livraison SAGE X3", readonly=True)
    sage_x3_last_import_date = fields.Datetime(string="Dernier import", readonly=True)
    type_command = fields.Selection([
        ('normal', 'Normale'),
        ('urgent', 'Urgente'),
    ], string="Type de commande", default='normal', copy=False)
    type_supplier = fields.Selection([
        ('vridi', 'VRIDI'),
        ('local', 'Local/Autres'),
    ], string="Type de fournisseur", default='vridi', copy=False)

    # def action_verify_product(self):
    #     for order in self:
    #         inactive_products = []
    #         dormant_products = []

    #         for line in order.order_line:
    #             product = line.product_id

    #             if product.actif_x3 != '1':
    #                 inactive_products.append(product.name)

    #             if not product.current_company_status_id or product.current_company_status_id.code != 'C':
    #                 dormant_products.append(product.name)

    #         messages = []

    #         if inactive_products:
    #             messages.append(_(
    #                 "Produits non actifs pour SAGE X3 :\n- %s"
    #             ) % "\n- ".join(inactive_products))

    #         if dormant_products:
    #             messages.append(_(
    #                 "Produits Dormants :\n- %s"
    #             ) % "\n- ".join(dormant_products))

    #         if messages:
    #             raise UserError("\n\n".join(messages))


    def action_verify_product(self):
        for order in self:
            products = order.order_line.mapped('product_id')

            inactive_products = products.filtered(
                lambda p: p.actif_x3 != '1'
            )
            dormant_products = products.filtered(
                lambda p: not p.current_company_status_id or p.current_company_status_id.code != 'C'
            )
            zero_lines = products.filtered(
                lambda l: l.product_id and l.price_unit == 0
            )

            messages = []

            if inactive_products:
                messages.append(_(
                    "Produits non actifs pour SAGE X3 :\n- %s"
                ) % "\n- ".join(inactive_products.mapped('display_name')))

            if dormant_products:
                messages.append(_(
                    "Produits Dormants :\n- %s"
                ) % "\n- ".join(dormant_products.mapped('display_name')))

            if zero_lines:
                messages.append(_(
                    "Produits Prix 0 :\n- %s"
                ) % "\n- ".join(zero_lines.mapped('display_name')))

            if messages:
                raise UserError("\n\n".join(messages))

    def action_pending_to_sage_x3(self):
        self.action_verify_product()
        self.write({'state': 'sent'})

    def button_confirm_local(self):
        
        for order in self:
            zero_lines = order.order_line.filtered(
                lambda l: l.product_id and l.price_unit == 0
            )
            if zero_lines:
                names = '\n- '.join(zero_lines.mapped('product_id.display_name'))
                raise UserError(_(
                    "Impossible de confirmer la commande.\n\n"
                    "Ces articles ont un prix unitaire à 0 FCFA :\n- %s\n\n"
                    "Veuillez renseigner un prix avant de confirmer."
                ) % names)
        res = super().button_confirm()
        return res

    def button_draft(self):
        res = super().button_draft()
        if self.type_supplier == 'vridi' and self.type_command == 'normal' and self.sage_x3_submitted:
            self.sage_x3_submitted = False
        return res