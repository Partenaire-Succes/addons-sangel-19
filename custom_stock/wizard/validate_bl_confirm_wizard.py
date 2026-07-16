from odoo import models, fields


class ValidateBLConfirmWizard(models.TransientModel):
    _name = 'validate.bl.confirm.wizard'
    _description = "Confirmation de validation du bon de livraison"

    picking_ids = fields.Many2many('stock.picking', string="Bons de livraison")

    def action_confirm(self):
        """L'utilisateur a confirmé → on relance la validation avec le flag
        de contexte pour ne pas re-proposer la confirmation."""
        return self.picking_ids.with_context(
            bl_validate_confirmed=True
        ).button_validate()
