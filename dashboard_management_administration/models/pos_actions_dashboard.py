import logging

from odoo import models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosActionsDashboard(models.Model):
    _name        = 'pos.actions.dashboard'
    _description = 'Dashboard POS et Actions'

    # =========================================================================
    # HELPERS INTERNES
    # =========================================================================

    def _check_group(self, *xml_ids):
        """
        Retourne True si l'utilisateur appartient à AU MOINS un des groupes listés.
        Centralise la vérification pour éviter la duplication.
        """
        return any(self.env.user.has_group(g) for g in xml_ids)

    def _permission_denied(self, message=None):
        """Retourne une notification d'accès refusé standardisée."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title':   'Accès refusé',
                'message': message or "Vous n'avez pas les permissions nécessaires pour cette action.",
                'type':    'warning',
                'sticky':  False,
            },
        }

    def _notify(self, title, message, notif_type='success', sticky=False):
        """Raccourci pour retourner une notification simple."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title':   title,
                'message': message,
                'type':    notif_type,
                'sticky':  sticky,
            },
        }

    # =========================================================================
    # DONNÉES DU DASHBOARD
    # =========================================================================

    @api.model
    def get_dashboard_data(self):
        """Retourne toutes les données du dashboard filtrées par société."""
        company_id = self.env.company.id
        return {
            'pos_configs':  self._get_pos_configs(company_id),
            'statistics':   self._get_statistics(company_id),
        }

    def _get_pos_configs(self, company_id):
        """Retourne les points de vente avec leur session active ou dernière session fermée."""
        pos_configs = self.env['pos.config'].search(
            [('company_id', '=', company_id)], order='name'
        )

        data = []
        for config in pos_configs:
            active_session = self.env['pos.session'].search([
                ('config_id', '=', config.id),
                ('state',     '=', 'opened'),
            ], limit=1)

            last_closed_session = self.env['pos.session'].search([
                ('config_id', '=', config.id),
                ('state',     '=', 'closed'),
            ], order='stop_at desc', limit=1)

            session_state = 'closed'
            session_info  = False

            if active_session:
                session_state = 'opened'
                session_info  = {
                    'id':           active_session.id,
                    'name':         active_session.name,
                    'user':         active_session.user_id.name,
                    'start_at':     active_session.start_at.strftime('%Y-%m-%d %H:%M')
                                    if active_session.start_at else '',
                    'order_count':  len(active_session.order_ids),
                    'total_amount': sum(active_session.order_ids.mapped('amount_total')),
                }
            elif last_closed_session:
                session_info = {
                    'id':           last_closed_session.id,
                    'name':         last_closed_session.name,
                    'user':         last_closed_session.user_id.name,
                    'stop_at':      last_closed_session.stop_at.strftime('%Y-%m-%d %H:%M')
                                    if last_closed_session.stop_at else '',
                    'order_count':  len(last_closed_session.order_ids),
                    'total_amount': sum(last_closed_session.order_ids.mapped('amount_total')),
                }

            data.append({
                'id':               config.id,
                'name':             config.name,
                'state':            session_state,
                'session_info':     session_info,
                'picking_type_id':  config.picking_type_id.name if config.picking_type_id else '',
                'journal_id':       config.journal_id.name if config.journal_id else '',
            })

        return data

    def _get_statistics(self, company_id):
        """Retourne les compteurs affichés sur le dashboard."""
        return {
            # Produits accessibles à cette société
            'product_count': self.env['product.template'].search_count([
                '|',
                ('company_id', '=', company_id),
                ('company_id', '=', False),
            ]),

            # Contacts accessibles à cette société
            'contact_count': self.env['res.partner'].search_count([
                '|',
                ('company_id', '=', company_id),
                ('company_id', '=', False),
            ]),

            # Commandes en attente de soumission à SAGE X3
            'purchase_to_validate': self.env['purchase.order'].search_count([
                ('company_id',        '=',  company_id),
                ('state',             'in', ['sent']),
                ('sage_x3_submitted', '=',  False),
                ('sage_x3_validated', '=',  False),
            ]),

            # FIX : utilise sage_x3_sent (pas sage_x3_submitted qui n'existe pas sur account.move)
            # Ne compte que les factures clients hors POS non encore envoyées
            'invoices_to_send': self.env['account.move'].search_count([
                ('company_id',     '=',  company_id),
                ('move_type',      '=',  'out_invoice'),
                ('state',          '=',  'posted'),
                ('sage_x3_sent',   '=',  False),
                ('pos_order_ids',  '=',  False),
            ]),

            # Commandes validées par SAGE X3 mais livraison non encore reçue
            'purchase_to_receive': self.env['purchase.order'].search_count([
                ('company_id',                '=',  company_id),
                ('state',                     'in', ['purchase']),
                ('sage_x3_submitted',         '=',  True),
                ('sage_x3_validated',         '=',  True),
                ('sage_x3_delivery_received', '=',  False),
            ]),

            # Sessions POS ouvertes
            'open_sessions': self.env['pos.session'].search_count([
                ('company_id', '=', company_id),
                ('state',      '=', 'opened'),
            ]),

            # Nombre de caisses configurées
            'pos_count': self.env['pos.config'].search_count([
                ('company_id', '=', company_id),
            ]),
        }

    # =========================================================================
    # ACTIONS DASHBOARD
    # =========================================================================

    @api.model
    def action_import_products(self, *args, **kwargs):
        """Import des produits depuis SAGE X3 (réservé DSI/IT)."""
        if not self._check_group('custom_pos.group_dsi_it'):
            return self._permission_denied(
                "Vous n'avez pas les permissions nécessaires pour importer les produits."
            )
        return self.env['product.template'].action_import_products_external_source()

    @api.model
    def action_import_contacts(self, *args, **kwargs):
        """Import des contacts depuis SAGE X3 (réservé DSI/IT).
        
        FIX : la méthode s'appelle action_import_contacts_external_source
        (pas action_import_from_external_source).
        """
        if not self._check_group('custom_pos.group_dsi_it'):
            return self._permission_denied(
                "Vous n'avez pas les permissions nécessaires pour importer les contacts."
            )
        return self.env['res.partner'].action_import_contacts_external_source()

    @api.model
    def action_import_all_data(self, *args, **kwargs):
        """Import produits ET contacts en une seule action (réservé DSI/IT)."""
        if not self._check_group('custom_pos.group_dsi_it'):
            return self._permission_denied(
                "Vous n'avez pas les permissions nécessaires pour importer les données."
            )

        errors   = []
        messages = []

        # Import des produits
        try:
            self.env['product.template'].action_import_products_external_source()
            messages.append("✅ Produits importés avec succès")
        except Exception as e:
            errors.append(f"❌ Erreur import produits : {str(e)}")
            _logger.exception("Erreur import produits depuis dashboard : %s", str(e))

        # Import des contacts
        try:
            self.env['res.partner'].action_import_contacts_external_source()
            messages.append("✅ Contacts importés avec succès")
        except Exception as e:
            errors.append(f"❌ Erreur import contacts : {str(e)}")
            _logger.exception("Erreur import contacts depuis dashboard : %s", str(e))

        all_lines     = messages + errors
        notif_type    = 'success' if not errors else ('warning' if messages else 'danger')
        title         = 'Import données' if not errors else 'Import terminé avec erreurs'

        return self._notify(title, "\n".join(all_lines), notif_type, sticky=bool(errors))

    @api.model
    def action_validate_purchases(self, *args, **kwargs):
        """Soumet les commandes en attente à SAGE X3 (DSI/IT ou responsable magasin)."""
        if not self._check_group(
            'custom_pos.group_dsi_it',
            'custom_pos.group_responsable_magasin',
        ):
            return self._permission_denied(
                "Vous n'avez pas les permissions nécessaires pour valider les achats."
            )
        return self.env['purchase.order'].action_submit_all_pending_to_sage_x3()

    @api.model
    def action_receive_purchases(self, *args, **kwargs):
        """Importe les livraisons SAGE X3 (DSI/IT ou responsable magasin)."""
        if not self._check_group(
            'custom_pos.group_dsi_it',
            'custom_pos.group_responsable_magasin',
        ):
            return self._permission_denied(
                "Vous n'avez pas les permissions nécessaires pour réceptionner les achats."
            )
        return self.env['purchase.order'].action_import_all_receive_external_source()

    @api.model
    def action_send_invoices_x3(self, *args, **kwargs):
        """
        Ouvre le wizard d'envoi des factures à SAGE X3.
        Accessible aux DSI/IT, superviseurs et assistants magasin.

        FIX 1 : 'super' était utilisé comme nom de variable (masque le builtin Python).
        FIX 2 : le filtre vérifie maintenant sage_x3_sent=False pour ne compter
                 que les factures réellement en attente d'envoi.
        """
        if not self._check_group(
            'custom_pos.group_dsi_it',
            'custom_pos.group_superviseur',
            'custom_pos.group_assistant_magasin',
        ):
            return self._permission_denied(
                "Vous n'avez pas les permissions nécessaires pour envoyer les factures à SAGE X3."
            )

        company_id = self.env.company.id

        # FIX : filtre sur sage_x3_sent=False (factures non encore envoyées uniquement)
        pending_invoices = self.env['account.move'].search_count([
            ('company_id',   '=',  company_id),
            ('move_type',    'in', ['out_invoice', 'out_refund']),
            ('state',        '=',  'posted'),
            ('sage_x3_sent', '=',  False),
        ])

        if not pending_invoices:
            return self._notify(
                'Information',
                'Aucune facture en attente d\'envoi à SAGE X3.',
                'warning',
            )

        return {
            'type':      'ir.actions.act_window',
            'name':      'Sélectionner la période',
            'res_model': 'sage.x3.send.wizard',
            'views':     [[False, 'form']],
            'target':    'new',
            'context':   {'default_company_id': company_id},
        }

    @api.model
    def action_process_documents(self, *args, **kwargs):
        """
        Valide les achats en attente et envoie les factures à SAGE X3.
        Accessible aux DSI/IT, superviseurs et assistants magasin.

        FIX : les vraies méthodes sont maintenant appelées
        (l'original avait des commentaires "REMPLACEZ par votre vraie méthode"
        sans appel réel).
        """
        if not self._check_group(
            'custom_pos.group_dsi_it',
            'custom_pos.group_superviseur',
            'custom_pos.group_assistant_magasin',
        ):
            return self._permission_denied(
                "Vous n'avez pas les permissions nécessaires pour traiter les documents."
            )

        company_id = self.env.company.id
        errors     = []
        messages   = []

        # 1. Soumission des commandes d'achat à SAGE X3
        try:
            purchases = self.env['purchase.order'].search([
                ('company_id',        '=',  company_id),
                ('state',             'in', ['sent']),
                ('sage_x3_submitted', '=',  False),
                ('sage_x3_validated', '=',  False),
            ])
            if purchases:
                self.env['purchase.order'].action_submit_all_pending_to_sage_x3()
                messages.append(f"✅ {len(purchases)} achat(s) soumis à SAGE X3")
            else:
                messages.append("ℹ️ Aucun achat à soumettre")
        except Exception as e:
            errors.append(f"❌ Erreur soumission achats : {str(e)}")
            _logger.exception("Erreur soumission achats depuis dashboard : %s", str(e))

        # 2. Envoi des factures hors POS à SAGE X3 via le wizard
        try:
            pending_invoices = self.env['account.move'].search([
                ('company_id',    '=',  company_id),
                ('move_type',     '=',  'out_invoice'),
                ('state',         '=',  'posted'),
                ('sage_x3_sent',  '=',  False),
                ('pos_order_ids', '=',  False),
            ])
            if pending_invoices:
                self.env['account.move']._process_bulk_send_classic_invoices_to_sage_x3(
                    pending_invoices.ids
                )
                messages.append(f"✅ {len(pending_invoices)} facture(s) envoyée(s) à SAGE X3")
            else:
                messages.append("ℹ️ Aucune facture à envoyer")
        except Exception as e:
            errors.append(f"❌ Erreur envoi factures : {str(e)}")
            _logger.exception("Erreur envoi factures depuis dashboard : %s", str(e))

        all_lines  = messages + errors
        notif_type = 'success' if not errors else ('warning' if messages else 'danger')
        title      = 'Traitement documents' if not errors else 'Traitement terminé avec erreurs'

        return self._notify(title, "\n".join(all_lines), notif_type, sticky=bool(errors))