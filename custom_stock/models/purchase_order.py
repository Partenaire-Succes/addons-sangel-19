from odoo import fields, models, api, _
from odoo.exceptions import UserError

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

    def action_pending_to_sage_x3(self):
        for order in self:
            inactive_products = []
            dormant_products = []

            for line in order.order_line:
                product = line.product_id

                if product.actif_x3 != '1':
                    inactive_products.append(product.name)

                if not product.current_company_status_id or product.current_company_status_id.code != 'C':
                    dormant_products.append(product.name)

            messages = []

            if inactive_products:
                messages.append(_(
                    "Produits non actifs pour SAGE X3 :\n- %s"
                ) % "\n- ".join(inactive_products))

            if dormant_products:
                messages.append(_(
                    "Produits Dormants :\n- %s"
                ) % "\n- ".join(dormant_products))

            if messages:
                raise UserError("\n\n".join(messages))

            order.write({'state': 'sent'})

    def button_confirm_local(self):
        self.button_confirm()


    def button_confirm(self):
        res = super().button_confirm()
        moves = self.action_create_invoice()
        return res