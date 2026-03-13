from odoo import fields, models, api, _

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

    state = fields.Selection(selection_add=[
        ('x3_pending', 'En attente X3'),
    ])

    def action_pending_to_sage_x3(self):
        self.write({'state': 'x3_pending'})