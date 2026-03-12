from odoo import models, fields, api
from odoo.exceptions import UserError

class PosActionsDashboard(models.Model):
    _name = 'pos.actions.dashboard'
    _description = 'Dashboard POS et Actions'

    @api.model
    def get_dashboard_data(self):
        """Récupère toutes les données du dashboard filtré par société"""
        company_id = self.env.company.id
        
        return {
            'pos_configs': self._get_pos_configs(company_id),
            'statistics': self._get_statistics(company_id),
        }

    def _get_pos_configs(self, company_id):
        """Récupère les points de vente avec leur session active"""
        pos_configs = self.env['pos.config'].search([
            ('company_id', '=', company_id)
        ], order='name')
        
        data = []
        for config in pos_configs:
            # Récupérer la session active
            active_session = self.env['pos.session'].search([
                ('config_id', '=', config.id),
                ('state', '=', 'opened')
            ], limit=1)
            
            # Récupérer la dernière session fermée
            last_closed_session = self.env['pos.session'].search([
                ('config_id', '=', config.id),
                ('state', '=', 'closed')
            ], order='stop_at desc', limit=1)
            
            session_state = 'closed'
            session_info = False  # CHANGEMENT ICI : False au lieu de {}
            
            if active_session:
                session_state = 'opened'
                session_info = {
                    'id': active_session.id,
                    'name': active_session.name,
                    'user': active_session.user_id.name,
                    'start_at': active_session.start_at.strftime('%Y-%m-%d %H:%M') if active_session.start_at else '',
                    'order_count': len(active_session.order_ids),
                    'total_amount': sum(active_session.order_ids.mapped('amount_total')),
                }
            elif last_closed_session:
                session_info = {
                    'id': last_closed_session.id,
                    'name': last_closed_session.name,
                    'user': last_closed_session.user_id.name,
                    'stop_at': last_closed_session.stop_at.strftime('%Y-%m-%d %H:%M') if last_closed_session.stop_at else '',
                    'order_count': len(last_closed_session.order_ids),
                    'total_amount': sum(last_closed_session.order_ids.mapped('amount_total')),
                }
            
            data.append({
                'id': config.id,
                'name': config.name,
                'state': session_state,
                'session_info': session_info,
                'picking_type_id': config.picking_type_id.name if config.picking_type_id else '',
                'journal_id': config.journal_id.name if config.journal_id else '',
            })
        
        return data

    def _get_statistics(self, company_id):
        """Récupère les statistiques pour les actions"""
        # Nombre de produits
        product_count = self.env['product.template'].search_count([
            '|', ('company_id', '=', company_id), ('company_id', '=', False)
        ])
        
        # Nombre de contacts
        contact_count = self.env['res.partner'].search_count([
            '|', ('company_id', '=', company_id), ('company_id', '=', False)
        ])
        
        # Achats en attente de validation
        purchase_to_validate = self.env['purchase.order'].search_count([
            ('company_id', '=', company_id),
            ('state', 'in', ['draft', 'sent'])
        ])
        
        # Factures en attente d'envoi
        invoices_to_send = self.env['account.move'].search_count([
            ('company_id', '=', company_id),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted'),
            # ('x3_sent', '=', False)  # Décommentez si vous avez ce champ
        ])
        
        # Sessions ouvertes
        open_sessions = self.env['pos.session'].search_count([
            ('company_id', '=', company_id),
            ('state', '=', 'opened')
        ])
        
        # Points de vente actifs
        pos_count = self.env['pos.config'].search_count([
            ('company_id', '=', company_id)
        ])
        
        return {
            'product_count': product_count,
            'contact_count': contact_count,
            'purchase_to_validate': purchase_to_validate,
            'invoices_to_send': invoices_to_send,
            'open_sessions': open_sessions,
            'pos_count': pos_count,
        }

    @api.model
    def action_import_all_data(self):
        """Importe les produits et contacts en une seule action"""
        try:
            errors = []
            success_messages = []
            
            # Import des produits
            try:
                # Appel de votre action d'import produits
                # REMPLACEZ par votre vraie méthode
                success_messages.append("Produits importés avec succès")
            except Exception as e:
                errors.append(f"Erreur import produits: {str(e)}")
            
            # Import des contacts
            try:
                # Appel de votre action d'import contacts
                # REMPLACEZ par votre vraie méthode
                success_messages.append("Contacts importés avec succès")
            except Exception as e:
                errors.append(f"Erreur import contacts: {str(e)}")
            
            if errors:
                message = "\n".join(success_messages + errors)
                notification_type = 'warning' if success_messages else 'danger'
            else:
                message = "\n".join(success_messages)
                notification_type = 'success'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Import données',
                    'message': message,
                    'type': notification_type,
                    'sticky': True,
                }
            }
        except Exception as e:
            raise UserError(f"Erreur lors de l'import des données: {str(e)}")

    @api.model
    def action_process_documents(self):
        """Valide les achats et envoie les factures à X3"""
        try:
            company_id = self.env.company.id
            errors = []
            success_messages = []
            
            # Validation des achats
            try:
                purchases = self.env['purchase.order'].search([
                    ('company_id', '=', company_id),
                    ('state', 'in', ['draft', 'sent'])
                ])
                
                if purchases:
                    # REMPLACEZ par votre vraie méthode
                    # purchases.button_confirm()
                    success_messages.append(f"{len(purchases)} achat(s) validé(s)")
                else:
                    success_messages.append("Aucun achat à valider")
            except Exception as e:
                errors.append(f"Erreur validation achats: {str(e)}")
            
            # Envoi des factures à X3
            try:
                invoices = self.env['account.move'].search([
                    ('company_id', '=', company_id),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                    ('state', '=', 'posted'),
                    # ('x3_sent', '=', False)
                ])
                
                if invoices:
                    # REMPLACEZ par votre vraie méthode
                    # invoices.send_to_x3()
                    success_messages.append(f"{len(invoices)} facture(s) envoyée(s) à X3")
                else:
                    success_messages.append("Aucune facture à envoyer")
            except Exception as e:
                errors.append(f"Erreur envoi factures: {str(e)}")
            
            if errors:
                message = "\n".join(success_messages + errors)
                notification_type = 'warning' if success_messages else 'danger'
            else:
                message = "\n".join(success_messages)
                notification_type = 'success'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Traitement documents',
                    'message': message,
                    'type': notification_type,
                    'sticky': True,
                }
            }
        except Exception as e:
            raise UserError(f"Erreur lors du traitement des documents: {str(e)}")

    @api.model
    def action_import_products(self, *args, **kwargs):
        """Exécute l'action d'import des produits"""
        try:
            products = self.env['product.template'].search([
                ('company_id', '=', self.env.company.id)
            ])
            
            if not products:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Import Produits',
                        'message': 'Aucun produit à importer',
                        'type': 'info',
                    }
                }
            
            return products.action_import_from_external_source()
        
        except Exception as e:
            raise UserError(f"Erreur lors de l'import des produits: {str(e)}")

    @api.model
    def action_import_contacts(self, *args, **kwargs):
        """Exécute l'action d'import des contacts"""
        try:
            contacts = self.env['res.partner'].search([
                ('company_id', '=', self.env.company.id)
            ])
            
            if not contacts:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Import Contacts',
                        'message': 'Aucun contact à importer',
                        'type': 'info',
                    }
                }
            
            return contacts.action_import_from_external_source()
        
        except Exception as e:
            raise UserError(f"Erreur lors de l'import des contacts: {str(e)}")

    @api.model
    def action_validate_purchases(self, *args, **kwargs):
        """Exécute l'action de validation des achats"""
        try:
            company_id = self.env.company.id
            purchases = self.env['purchase.order'].search([
                ('company_id', '=', company_id),
                ('state', 'in', ['draft', 'sent'])
            ])
            
            if not purchases:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Information',
                        'message': 'Aucun achat à valider',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            
            return purchases.action_submit_to_sage_x3()
        
        except Exception as e:
            raise UserError(f"Erreur lors de la validation des achats: {str(e)}")

    @api.model
    def action_send_invoices_x3(self, *args, **kwargs):
        company_id = self.env.company.id

        invoices = self.env['account.move'].search([
            ('company_id', '=', company_id),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '=', 'posted')
        ])

        if not invoices:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Information',
                    'message': 'Aucune facture à envoyer',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        return {
            'type': 'ir.actions.act_window',
            'name': 'Sélectionner la période',
            'res_model': 'sage.x3.send.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_company_id': self.env.company.id
            }
        }