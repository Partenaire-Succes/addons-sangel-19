from odoo import api, fields, models, _
from datetime import datetime, timedelta
from markupsafe import Markup, escape as html_escape
from odoo.exceptions import UserError
import logging
import json

_logger = logging.getLogger(__name__)


class ProductPriceHistory(models.Model):
    _name = 'product.price.history'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Historique des prix produits'
    _order = 'date_changed desc'
    _rec_name = 'product_id'

    product_id = fields.Many2one(
        comodel_name='product.template',
        string='Produit',
        required=True
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Devise',
        required=True,
        default=lambda self: self.env.company.currency_id
    )

    old_price = fields.Float(
        string='Ancien prix',
        digits='Product Price'
    )

    new_price = fields.Float(
        string='Nouveau prix',
        digits='Product Price'
    )

    date_changed = fields.Datetime(
        string='Date de modification',
        default=fields.Datetime.now
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Modifié par',
        default=lambda self: self.env.user
    )

    notified = fields.Boolean(
        string='Notifié',
        default=False,
        tracking=True
    )

    price_difference = fields.Float(
        string='Différence',
        compute='_compute_price_difference',
        store=True
    )

    price_change_percent = fields.Float(
        string='Pourcentage de changement (%)',
        compute='_compute_price_difference',
        store=True
    )

    state = fields.Selection(
        selection=[
            ('draft', 'En attente'),
            ('notified', 'Notifié'),
        ],
        string='Statut',
        default='draft'
    )

    print_state = fields.Selection(
        selection=[
            ('draft', "En attente"),
            ('printed', 'Imprimé'),
        ],
        string='Statut Impression',
        default='draft'
    )


    def action_print_product_label(self):
        """Imprimer des étiquettes pour un ou plusieurs historiques"""
        if not self:
            return False

        Layout = self.env['product.label.layout']
        product_templates = self.mapped('product_id')

        wizard = Layout.create({
            'product_tmpl_ids': [(6, 0, product_templates.ids)],
        })

        xml_id, data = wizard._prepare_report_data()
        xml_ref = xml_id[0] if isinstance(xml_id, (list, tuple)) else xml_id

        report = self.env.ref(xml_ref, raise_if_not_found=False) \
                 or self.env['ir.actions.report']._get_report_from_name(xml_ref) \
                 or self.env['ir.actions.report']._get_report_from_name('stock.label_product_product_view')

        if not report:
            raise UserError(_("Impossible de trouver le rapport d'étiquettes (%s).") % xml_ref)

        # 📌 Ici : changer l'état à "printed"
        self.write({'print_state': 'printed'})

        action = report.report_action(None, data=data)
        action.update({'close_on_report_download': True})
        return action

    def action_mark_as_notified(self):
        self.write({'notified': True})
        self.write({'state': 'notified'})
        return True

    def action_mark_as_not_notified(self):
        self.write({'notified': False})
        self.write({'state': 'draft'})
        return True


    @api.depends('old_price', 'new_price')
    def _compute_price_difference(self):
        for record in self:
            record.price_difference = record.new_price - record.old_price
            if record.old_price != 0:
                record.price_change_percent = ((record.new_price - record.old_price) / record.old_price) * 100
            else:
                record.price_change_percent = 0.0

    @api.model
    def _get_or_create_price_notification_channel(self):
        """Créer ou récupérer le canal de notification des prix"""
        channel_name = "Notifications sur le changement de prix"

        # Chercher un canal existant
        channel = self.env['discuss.channel'].search([
            ('name', '=', channel_name),
            ('channel_type', '=', 'channel')
        ], limit=1)

        if not channel:
            # Créer le canal s'il n'existe pas
            channel = self.env['discuss.channel'].create({
                'name': channel_name,
                'description': 'Canal automatique pour les notifications de changement de prix',
                'channel_type': 'channel',
                # 'public': 'private',  # Canal privé
            })
            _logger.info("✅ Canal '%s' créé avec succès", channel_name)

        return channel


    @api.model
    def _add_users_to_channel(self, channel, users):
        """Ajouter plusieurs utilisateurs au canal"""
        partners = users.mapped("partner_id")
        new_partners = partners - channel.channel_partner_ids
        if new_partners:
            # ✅ Correction : utiliser add_members correctement
            channel.write({'channel_partner_ids': [(4, pid) for pid in new_partners.ids]})
            _logger.info("✅ %d utilisateurs ajoutés au canal %s", len(new_partners), channel.name)

    # Corrections dans send_daily_price_notifications

    @api.model
    def send_daily_price_notifications(self, *args):
        """Méthode appelée par le cron -> model.send_daily_price_notifications()"""
        try:
            param_env = self.env['ir.config_parameter'].sudo()

            # ✅ Vérifier si les notifications sont activées
            if param_env.get_param('custom_price_change_tracker.notification_active', 'False') != 'True':
                _logger.info("Notifications de prix désactivées.")
                return

            # ✅ Récupération du Many2many (JSON)
            user_ids_param = param_env.get_param(
                'custom_price_change_tracker.price_notification_user_ids', '[]'
            )
            try:
                user_ids = json.loads(user_ids_param)
            except (json.JSONDecodeError, ValueError):
                user_ids = []

            users = self.env['res.users'].browse(user_ids).exists()
            if not users:
                _logger.info("Aucun utilisateur configuré pour la notification de prix.")
                return

            # ✅ Calculer correctement "hier"
            yesterday = fields.Datetime.now() - timedelta(days=1)
            price_changes = self.search([
                ('date_changed', '>=', yesterday),
                ('notified', '=', False)
            ])

            if not price_changes:
                _logger.info("Aucun changement de prix à notifier.")
                return

            # Récupérer ou créer le canal
            channel = self._get_or_create_price_notification_channel()

            # Ajouter les utilisateurs au canal
            self._add_users_to_channel(channel, users)

            # Récupérer la devise de la société
            currency_symbol = self.env.company.currency_id.symbol or self.env.company.currency_id.name

            # Préparer la liste des IDs
            price_change_ids = price_changes.ids

            message_lines = ["<b>📊 Changements de prix détectés</b><br/><br/>"]
            for change in price_changes:
                symbol = "📈" if change.price_difference > 0 else "📉"
                message_lines.append(
                    "%s <b>%s</b><br/>Ancien: %.0f %s → Nouveau: <b>%.0f %s</b><br/>Diff: %+0.2f %s (%+0.1f%%)<br/><br/>" % (
                        symbol,
                        html_escape(change.product_id.display_name or "Produit"),
                        change.old_price,
                        currency_symbol,
                        change.new_price,
                        currency_symbol,
                        change.price_difference,
                        currency_symbol,
                        change.price_change_percent,
                    )
                )

            # ✅ Créer l'URL correctement
            try:
                action_xmlid = 'custom_price_change_tracker.action_products_price_history'
                action = self.env.ref(action_xmlid, raise_if_not_found=False)

                if action:
                    history_list_url = f"/web#action={action.id}&view_type=list&cids=1&domain=[('id','in',[{','.join(map(str, price_change_ids))}])]"
                else:
                    history_list_url = f"/web#model=product.price.history&view_type=list&domain=[('id','in',[{','.join(map(str, price_change_ids))}])]"
            except Exception:
                history_list_url = f"/web#model=product.price.history&view_type=list&domain=[('id','in',[{','.join(map(str, price_change_ids))}])]"

            message_lines.append(
                f"<b>🏷️ <a href='{history_list_url}' target='_self' style='color: #007bff; text-decoration: none; font-weight: bold;'>➤ Voir la liste des produits pour impression d'étiquettes</a></b>"
            )

            # ✅ Envoyer le message dans le canal
            channel.message_post(
                body=Markup(''.join(message_lines)),
                message_type='comment',
                subtype_xmlid='mail.mt_comment'
            )

            # ✅ Marquer comme notifié
            price_changes.write({
                'notified': True,
                'state': 'notified'
            })

            _logger.info("✅ Notification envoyée dans le canal '%s' pour %d changements", channel.name,
                         len(price_changes))

            return True

        except Exception as e:
            _logger.error("❌ Erreur notification prix: %s", str(e), exc_info=True)
            return False