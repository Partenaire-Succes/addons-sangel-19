from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

class SageX3SendWizard(models.TransientModel):
    _name = 'sage.x3.send.wizard'
    _description = 'Wizard envoi SAGE X3'

    date_from = fields.Date(
        string="Date début",
        required=True,
        default=fields.Date.today
    )
    date_to = fields.Date(
        string="Date fin",
        required=True,
        default=fields.Date.today
    )
    company_ids = fields.Many2many(
        'res.company',
        string="Sociétés",
        required=True,
        default=lambda self: self.env.company
    )
    
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Valide les dates"""
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError("La date de début doit être antérieure à la date de fin")
    
    def action_confirm_send(self):
        """Confirme et lance l'envoi"""
        self.ensure_one()
        
        # Lancer l'envoi groupé
        result = self.env['account.move']._process_bulk_send_to_sage_x3(
            self.date_from,
            self.date_to,
            self.company_ids.ids
        )
        
        # Préparer le message de résultat
        message = f"""📊 Résultat de l'envoi à SAGE X3

✅ Jours envoyés avec succès: {result['success']}
❌ Erreurs: {result['errors']}

Période: {self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')}
Sociétés: {', '.join(self.company_ids.mapped('name'))}
"""
        
        if result['error_details']:
            message += "\n\n⚠️ Détails des erreurs (10 premières):\n"
            for error in result['error_details'][:10]:
                message += f"• {error}\n"
            
            if len(result['error_details']) > 10:
                message += f"\n... et {len(result['error_details']) - 10} autre(s) erreur(s)"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Envoi terminé' if result['errors'] == 0 else '⚠️ Envoi terminé avec erreurs',
                'message': message,
                'type': 'success' if result['errors'] == 0 else 'warning',
                'sticky': True,
            }
        }