from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import calendar


class FoodCreditInvoiceWizard(models.TransientModel):
    _name = 'food.credit.invoice.wizard'
    _description = 'Food Credit Invoice Generation Wizard'
    
    food_ids = fields.Many2many(
        'food.credit', 
        string='Crédits Alimentaires', 
        domain=[('state', '=', 'in_progress'), ('amount_used', '>', 0)],
        required=True
    )
    date_start = fields.Datetime(
        string="Date de début", 
        required=True, 
        copy=False,
        default=lambda self: self._get_month_start(),
        help="Date fixée au 1er jour du mois à 00:00:00"
    )
    date_end = fields.Datetime(
        string="Date de fin", 
        required=True, 
        copy=False,
        default=lambda self: self._get_month_end(),
        help="Date fixée au dernier jour du mois à 23:59:59"
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain=[('type', '=', 'sale')],
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Produit Crédit Alimentaire',
        required=True,
        default=lambda self: self._get_default_product()
    )
    invoice_date = fields.Date(
        string='Date de facture',
        default=fields.Date.context_today,
        required=True
    )
    
    @api.model
    def default_get(self, fields_list):
        """Pré-remplir le wizard avec les crédits alimentaires éligibles"""
        res = super().default_get(fields_list)
        
        # Récupérer les crédits alimentaires éligibles
        credits = self.env['food.credit'].search([
            ('state', '=', 'in_progress'), 
            ('amount_used', '>', 0),
        ])
        res['food_ids'] = [(6, 0, credits.ids)]
        
        # Journal par défaut
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if journal:
            res['journal_id'] = journal.id
            
        return res
    
    def _get_month_start(self):
        """Retourne le premier jour du mois courant à 00:00:00"""
        now = fields.Datetime.now()
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    def _get_month_end(self):
        """Retourne le dernier jour du mois courant à 23:59:59"""
        now = fields.Datetime.now()
        # Trouver le dernier jour du mois
        last_day = calendar.monthrange(now.year, now.month)[1]
        return now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    
    @api.onchange('date_start')
    def _onchange_date_start(self):
        """Forcer la date de début au premier jour du mois sélectionné"""
        if self.date_start:
            self.date_start = self.date_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Ajuster automatiquement la date de fin au dernier jour du même mois
            last_day = calendar.monthrange(self.date_start.year, self.date_start.month)[1]
            self.date_end = self.date_start.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    
    @api.onchange('date_end')  
    def _onchange_date_end(self):
        """Forcer la date de fin au dernier jour du mois sélectionné"""
        if self.date_end:
            last_day = calendar.monthrange(self.date_end.year, self.date_end.month)[1]
            self.date_end = self.date_end.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    
    def _get_default_product(self):
        """Récupérer le produit crédit alimentaire par défaut"""
        try:
            product = self.env.ref('custom_food_credit.product_credit_food')
            return product.id if product else False
        except:
            # Fallback: recherche par nom si la référence échoue
            product = self.env['product.product'].search([
                ('name', '=', 'Crédit Alimentaire')
            ], limit=1)
            return product.id if product else False
    
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        """Validation des dates - doit être premier et dernier jour du mois"""
        for record in self:
            if record.date_start >= record.date_end:
                raise ValidationError("La date de fin doit être postérieure à la date de début.")
            
            # Vérifier que date_start est le 1er jour du mois à 00:00:00
            if (record.date_start.day != 1 or 
                record.date_start.hour != 0 or 
                record.date_start.minute != 0 or 
                record.date_start.second != 0):
                raise ValidationError("La date de début doit être le 1er jour du mois à 00:00:00")
            
            # Vérifier que date_end est le dernier jour du mois à 23:59:59
            last_day = calendar.monthrange(record.date_end.year, record.date_end.month)[1]
            if (record.date_end.day != last_day or 
                record.date_end.hour != 23 or 
                record.date_end.minute != 59 or 
                record.date_end.second != 59):
                raise ValidationError("La date de fin doit être le dernier jour du mois à 23:59:59")
    
    def action_generate_invoices(self):
        """Générer les factures pour les crédits alimentaires sélectionnés"""
        if not self.food_ids:
            raise UserError("Veuillez sélectionner au moins un crédit alimentaire.")
        
        if not self.product_id:
            raise UserError("Veuillez sélectionner le produit crédit alimentaire.")
        
        if not self.journal_id:
            raise UserError("Veuillez sélectionner un journal de vente.")
        
        # Filtrer les crédits selon la période sélectionnée
        filtered_credits = self.food_ids.filtered(
            lambda c: c.write_date >= self.date_start and c.write_date <= self.date_end
        )
        
        if not filtered_credits:
            raise UserError("Aucun crédit alimentaire trouvé dans la période sélectionnée.")
        
        created_invoices = self.env['account.move']
        invoice_vals_list = []
        errors = []
        
        for credit in filtered_credits:
            try:
                # Validations
                if not credit.partner_company_id:
                    errors.append(f"Crédit {credit.name or credit.id}: Aucun client défini")
                    continue
                    
                if credit.amount_used <= 0:
                    errors.append(f"Crédit {credit.name or credit.id}: Montant utilisé invalide ({credit.amount_used})")
                    continue
                
                if not credit.line_ids:
                    errors.append(f"Crédit {credit.name or credit.id}: Aucune ligne de crédit trouvée")
                    continue
                
                # Vérifier si une facture existe déjà pour ce crédit
                existing_invoice = self.env['account.move'].search([
                    ('ref', '=', credit.name),
                    ('partner_id', '=', credit.partner_company_id.id),
                    ('state', '!=', 'cancel')
                ], limit=1)
                
                if existing_invoice:
                    errors.append(f"Crédit {credit.name or credit.id}: Facture déjà existante ({existing_invoice.name})")
                    continue
                
                # Préparer les lignes de facture à partir des line_ids
                invoice_line_vals_list = []
                for line in credit.line_ids:
                    if line.amount_used > 0:  # Seulement les lignes avec un montant
                        invoice_line_vals = {
                            'product_id': self.product_id.id,
                            'name': f'Crédit Alimentaire - {line.partner_name}',
                            'quantity': 1,
                            'invoice_text': line.invoice_text,
                            'price_unit': line.amount_used,
                            'account_id': self.product_id.property_account_income_id.id or 
                                        self.product_id.categ_id.property_account_income_categ_id.id,
                        }
                        invoice_line_vals_list.append((0, 0, invoice_line_vals))
                
                # Vérifier qu'il y a des lignes à facturer
                if not invoice_line_vals_list:
                    errors.append(f"Crédit {credit.name or credit.id}: Aucune ligne avec montant > 0 trouvée")
                    continue
                
                # Préparer les valeurs de la facture
                invoice_vals = {
                    'move_type': 'out_invoice',
                    'partner_id': credit.partner_company_id.id,
                    'journal_id': self.journal_id.id,
                    'invoice_date': self.invoice_date,
                    'ref': credit.name,
                    'invoice_line_ids': invoice_line_vals_list,
                    'food_id': credit.id,  # Lien vers le crédit alimentaire
                }
                
                invoice_vals_list.append(invoice_vals)
                
            except Exception as e:
                errors.append(f"Crédit {credit.name or credit.id}: {str(e)}")
        
        # Créer les factures
        if invoice_vals_list:
            try:
                created_invoices = self.env['account.move'].create(invoice_vals_list)
                
                # Lier les factures aux crédits alimentaires via move_id

                for i, credit in enumerate([c for c in filtered_credits if not any(str(c.id) in error for error in errors)]):
                    if i < len(created_invoices):
                        credit.write({'move_id': created_invoices[i].id, 'invoiced': True})
                
            except Exception as e:
                raise UserError(f"Erreur lors de la création des factures: {str(e)}")
        
        # Préparer le message de résultat
        message_parts = []
        if created_invoices:
            message_parts.append(f"✅ {len(created_invoices)} facture(s) créée(s) avec succès.")
        
        if errors:
            message_parts.append(f"⚠️ {len(errors)} erreur(s) rencontrée(s):")
            message_parts.extend([f"  • {error}" for error in errors[:10]])  # Limiter à 10 erreurs
            if len(errors) > 10:
                message_parts.append(f"  • ... et {len(errors) - 10} autres erreurs")
        
        if not created_invoices and not errors:
            raise UserError("Aucune facture à créer.")
        
        # Afficher le message de résultat
        if message_parts:
            message = "\n".join(message_parts)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Génération des factures',
                    'message': message,
                    'type': 'success' if created_invoices else 'warning',
                    'sticky': True,
                }
            }
        
        if created_invoices:
            return {'type': 'ir.actions.act_window_close'}
            # return {
            #     'type': 'ir.actions.act_window_close',
            #     'name': 'Factures Créées',
            #     'res_model': 'account.move',
            #     'view_mode': 'tree,form',
            #     'domain': [('id', 'in', created_invoices.ids)],
            #     'context': {
            #         'default_move_type': 'out_invoice',
            #         'create': False,
            #     },
            #     'target': 'current',
            # }
    
    def action_preview_invoices(self):
        """Prévisualiser les factures qui seront créées"""
        if not self.food_ids:
            raise UserError("Veuillez sélectionner au moins un crédit alimentaire.")
        
        # Filtrer les crédits selon la période
        filtered_credits = self.food_ids.filtered(
            lambda c: c.write_date >= self.date_start and c.write_date <= self.date_end
        )
        
        preview_data = []
        total_amount = 0
        total_lines = 0
        
        for credit in filtered_credits:
            if credit.partner_company_id and credit.amount_used > 0 and credit.line_ids:
                # Compter les lignes avec montant > 0
                valid_lines = credit.line_ids.filtered(lambda l: l.amount_used > 0)
                line_count = len(valid_lines)
                
                if line_count > 0:
                    preview_data.append({
                        'partner_name': credit.partner_company_id.name,
                        'amount_used': credit.amount_used,
                        'credit_name': credit.name or f'Crédit {credit.id}',
                        'line_count': line_count
                    })
                    total_amount += credit.amount_used
                    total_lines += line_count
        
        message = f"Aperçu de la génération:\n\n"
        message += f"Nombre de factures à créer: {len(preview_data)}\n"
        message += f"Nombre total de lignes: {total_lines}\n"
        message += f"Montant total: {total_amount:.2f}\n\n"
        message += "Détail des factures:\n"
        
        for data in preview_data[:10]:  # Limiter à 10 pour l'affichage
            message += f"• {data['partner_name']}: {data['amount_used']:.2f} ({data['line_count']} lignes)\n"
        
        if len(preview_data) > 10:
            message += f"• ... et {len(preview_data) - 10} autres factures"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Aperçu de la génération',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }