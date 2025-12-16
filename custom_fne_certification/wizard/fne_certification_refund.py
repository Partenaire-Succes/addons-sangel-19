import json
import requests
from odoo.exceptions import UserError
from odoo import models, fields


class FNERefundWizard(models.TransientModel):
    _name = 'fne.refund.wizard'
    _description = "Wizard de certification FNE pour avoir"

    move_id = fields.Many2one(
        'account.move', 
        string='Facture',
        store=True,
        readonly=True
    )

    def action_certify_fne_refund(self):
        for refund in self:
            invoice = refund.move_id
            if not invoice:
                raise UserError("Aucune facture d’avoir sélectionnée.")
            if invoice.fne_certified:
                raise UserError("Cet avoir est déjà certifié FNE.")
            if not invoice.reversed_entry_id or not invoice.reversed_entry_id.fne_reference:
                raise UserError("La facture d’origine n’est pas certifiée FNE.")

            original_fne_id = invoice.reversed_entry_id.fne_invoice_uuid
            if not original_fne_id:
                raise UserError("Identifiant FNE de la facture d’origine manquant.")

            fne_config = self.env['fne.config.settings'].search([], limit=1)
            if not fne_config or not fne_config.fne_api_token:
                raise UserError("Configuration FNE manquante ou invalide.")

            # Préparer les lignes retournées
            refund_items = []
            for line in invoice.invoice_line_ids:
                if line.fne_original_line_id and line.quantity > 0:
                    refund_items.append({
                        "id": line.fne_original_line_id,
                        "quantity": line.quantity
                    })

            if not refund_items:
                raise UserError("Aucune ligne d’avoir valide à certifier.")

            payload = {
                "id": original_fne_id,
                "items": refund_items
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {fne_config.fne_api_token}"
            }

            url = f"http://54.247.95.108/ws/external/invoices/{original_fne_id}/refund"

            try:
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                data = response.json()

                if response.status_code in [200, 201]:
                    invoice.fne_certified = True
                    invoice.fne_reference = data.get("reference")
                    invoice.fne_token = data.get("token")
                    invoice.fne_sticker_balance = data.get("balance_sticker")
                    invoice.fne_response_json = json.dumps(data, indent=2)

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Avoir certifié FNE',
                            'message': f"Référence FNE : {invoice.fne_reference}",
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    raise UserError(f"Erreur FNE : {data.get('message') or response.text}")

            except requests.exceptions.RequestException as e:
                raise UserError(f"Erreur réseau vers FNE : {str(e)}")
