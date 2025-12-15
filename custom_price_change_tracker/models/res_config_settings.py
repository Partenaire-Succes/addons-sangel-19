from odoo import fields, models, api
import json


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    price_notification_user_id = fields.Many2one(
        'res.users',
        string='Utilisateur à notifier pour les changements de prix',
        config_parameter='custom_price_change_tracker.notification_user_id'
    )

    price_notification_user_ids = fields.Many2many(
        'res.users',
        string='Utilisateur à notifier pour les changements de prix',
    )

    price_notification_active = fields.Boolean(
        string='Activer les notifications de prix',
        config_parameter='custom_price_change_tracker.notification_active',
        default=True
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        param = self.env['ir.config_parameter'].sudo().get_param(
            'custom_price_change_tracker.price_notification_user_ids', default="[]"
        )
        try:
            res.update(
                price_notification_user_ids=[(6, 0, json.loads(param))]
            )
        except json.JSONDecodeError:
            res.update(price_notification_user_ids=[(6, 0, [])])
        return res

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'custom_price_change_tracker.price_notification_user_ids',
            json.dumps(self.price_notification_user_ids.ids)
        )

    def send_test_notification(self):
        """Méthode pour tester l'envoi de notifications"""
        user_id = self.env['ir.config_parameter'].sudo().get_param('custom_price_change_tracker.notification_user_id')
        if user_id:
            user = self.env['res.users'].browse(int(user_id))
            if user:
                user.notify_info(
                    message="Test de notification pour les changements de prix",
                    title="Test de notification",
                    sticky=False
                )
        return {'type': 'ir.actions.act_window_close'}