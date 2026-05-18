# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
from requests.auth import HTTPBasicAuth
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class X3Config(models.Model):
    """
    Configuration de connexion à un serveur Sage X3.
    Un enregistrement = un client/dossier X3.
    """
    _name = 'x3.config'
    _description = 'Configuration Sage X3'
    _rec_name = 'name'

    name = fields.Char(
        string='Nom de la configuration',
        required=True,
        help="Ex: Client ABC - Production"
    )
    active = fields.Boolean(default=True)

    # ── Connexion ────────────────────────────────────────────────────────────
    server_url = fields.Char(
        string='URL Serveur Syracuse',
        required=True,
        help="Ex: https://192.168.1.10 ou https://x3.monclient.com"
    )
    port = fields.Integer(
        string='Port',
        default=443,
        help="443 pour HTTPS, 28880 pour HTTP"
    )
    dossier = fields.Char(
        string='Dossier / Tenant X3',
        required=True,
        help="Nom du dossier X3 (ex: SEED, PROD, TEST...)"
    )
    pool = fields.Char(
        string='Pool X3',
        default='x3erp',
        help="Généralement 'x3erp'"
    )

    # ── Authentification ─────────────────────────────────────────────────────
    username = fields.Char(string='Utilisateur X3', required=True)
    password = fields.Char(string='Mot de passe X3', required=True)
    verify_ssl = fields.Boolean(
        string='Vérifier SSL',
        default=False,
        help="Désactiver si certificat auto-signé"
    )

    # ── Infos techniques ─────────────────────────────────────────────────────
    x3_version = fields.Selection([
        ('v7', 'Version 7'),
        ('v11', 'Version 11'),
        ('v12', 'Version 12'),
        ('v12pu9', 'Version 12 PU9+'),
    ], string='Version X3', default='v12')

    db_type = fields.Selection([
        ('mssql', 'SQL Server'),
        ('oracle', 'Oracle'),
    ], string='Type de BDD', default='mssql')

    # ── Statut ───────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Non testé'),
        ('ok', 'Connecté'),
        ('error', 'Erreur'),
    ], string='Statut', default='draft', readonly=True)

    last_test_date = fields.Datetime(string='Dernier test', readonly=True)
    last_error = fields.Text(string='Dernière erreur', readonly=True)

    # ── Logs ─────────────────────────────────────────────────────────────────
    log_ids = fields.One2many('x3.migration.log', 'config_id', string='Logs')
    log_count = fields.Integer(compute='_compute_log_count')

    @api.depends('log_ids')
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    def _get_base_url(self):
        """Construit l'URL de base SData."""
        self.ensure_one()
        url = self.server_url.rstrip('/')
        if self.port not in (80, 443):
            url = f"{url}:{self.port}"
        return f"{url}/sdata/{self.pool}/{self.dossier}"

    def _get_session(self):
        """Crée une session requests configurée."""
        self.ensure_one()
        session = requests.Session()
        session.auth = HTTPBasicAuth(self.username, self.password)
        session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        session.verify = self.verify_ssl
        return session

    def action_test_connection(self):
        """Teste la connexion au serveur X3."""
        self.ensure_one()
        try:
            session = self._get_session()
            base_url = self._get_base_url()

            # Test sur le plan comptable (objet léger)
            response = session.get(
                f"{base_url}/GACCOUN",
                params={'$top': 1},
                timeout=10
            )

            if response.status_code == 200:
                self.write({
                    'state': 'ok',
                    'last_test_date': fields.Datetime.now(),
                    'last_error': False,
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connexion réussie'),
                        'message': _(f'Connecté à {self.dossier} sur {self.server_url}'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise Exception(f"HTTP {response.status_code} : {response.text[:200]}")

        except Exception as e:
            self.write({
                'state': 'error',
                'last_test_date': fields.Datetime.now(),
                'last_error': str(e),
            })
            raise UserError(_(f"Erreur de connexion : {str(e)}"))

    def action_view_logs(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Logs de migration'),
            'res_model': 'x3.migration.log',
            'view_mode': 'tree,form',
            'domain': [('config_id', '=', self.id)],
            'context': {'default_config_id': self.id},
        }
