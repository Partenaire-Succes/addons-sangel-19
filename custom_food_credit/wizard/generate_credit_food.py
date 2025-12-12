from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime
from dateutil.relativedelta import relativedelta

import logging

_logger = logging.getLogger(__name__)

class FoodCreditGenerationWizard(models.TransientModel):
    _name = 'food.credit.generation.wizard'
    _description = 'Food Credit Generation Wizard'
    
    company_ids = fields.Many2many('res.partner', 
                                   string='Sociétés', 
                                   domain=[('is_company', '=', True), ('amount_food', '>', 0)])
    month = fields.Selection([
        ('1', 'Janvier'), ('2', 'Février'), ('3', 'Mars'), ('4', 'Avril'),
        ('5', 'Mai'), ('6', 'Juin'), ('7', 'Juillet'), ('8', 'Août'),
        ('9', 'Septembre'), ('10', 'Octobre'), ('11', 'Novembre'), ('12', 'Décembre')
    ], string='Mois', default=str(datetime.now().month)) 
    year = fields.Integer('Année', default=lambda self: datetime.now().year)
    overwrite_existing = fields.Boolean('Écraser les crédits existants', default=False)
    
    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        # Sélectionner toutes les sociétés par défaut
        companies = self.env['res.partner'].search([
            ('is_company', '=', True), 
            ('amount_food', '>', 0)
        ])
        res['company_ids'] = [(6, 0, companies.ids)]
        return res
    
    def action_generate(self):
        food_credit_obj = self.env['food.credit']

        # Convertir month en entier
        month_int = int(self.month)
        year_int = self.year
        
        # Calculer les dates
        start_date = datetime(year_int, month_int, 1)
        end_date = (start_date + relativedelta(months=1)) - relativedelta(days=1)
        
        months_fr = {
            1: 'JANVIER', 2: 'FÉVRIER', 3: 'MARS', 4: 'AVRIL',
            5: 'MAI', 6: 'JUIN', 7: 'JUILLET', 8: 'AOÛT',
            9: 'SEPTEMBRE', 10: 'OCTOBRE', 11: 'NOVEMBRE', 12: 'DÉCEMBRE'
        }
        month_name = months_fr[month_int]
        
        created_credits = []
        updated_credits = []
        total_lines = 0
        
        for company in self.company_ids:
            name = f"CREDIT/{month_name}/{year_int}/{company.name.upper()}"
            
            existing_credit = food_credit_obj.search([('name', '=', name)], limit=1)
            
            if existing_credit and not self.overwrite_existing:
                continue
            elif existing_credit and self.overwrite_existing:
                # Mettre à jour le crédit existant
                existing_credit.write({
                    'amount': company.amount_food,
                    'start': start_date.date(),
                    'end': end_date.date(),
                })
                lines_count = food_credit_obj._create_lines_for_credit(existing_credit)
                updated_credits.append(existing_credit)
                total_lines += lines_count
            else:
                # Créer nouveau crédit
                food_credit = food_credit_obj.create({
                    'name': name,
                    'partner_company_id': company.id,
                    'amount': company.amount_food,
                    'start': start_date.date(),
                    'end': end_date.date(),
                })
                lines_count = food_credit_obj._create_lines_for_credit(food_credit)
                created_credits.append(food_credit)
                total_lines += lines_count
        
        # Message de retour
        message_parts = []
        if created_credits:
            message_parts.append(f"{len(created_credits)} crédit(s) créé(s)")
        if updated_credits:
            message_parts.append(f"{len(updated_credits)} crédit(s) mis à jour")
        if total_lines:
            message_parts.append(f"{total_lines} ligne(s) générée(s)")
        
        return {'type': 'ir.actions.act_window_close'}
        # return {
        #     'type': 'ir.actions.client',
        #     'tag': 'display_notification',
        #     'params': {
        #         'title': 'Génération terminée',
        #         'message': " - ".join(message_parts) if message_parts else "Aucune action effectuée",
        #         'type': 'success',
        #     }
        # }