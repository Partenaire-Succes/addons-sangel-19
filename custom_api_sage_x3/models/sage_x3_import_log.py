import logging
from datetime import datetime

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SageX3ImportLog(models.TransientModel):
    _name = 'sage.x3.import.log'
    _description = 'Logs Import Sage X3'
    _order = 'created_at desc'

    sage_log_id = fields.Integer(string='ID Log', readonly=True)
    import_type = fields.Char(string='Type Import', readonly=True)
    import_model = fields.Char(string='Modèle Import', readonly=True)
    status = fields.Selection([
        ('Success', 'Succès'),
        ('Error', 'Erreur'),
        ('Warning', 'Avertissement'),
    ], string='Statut', readonly=True)
    reference_document = fields.Char(string='Référence Document', readonly=True)
    x3_document_number = fields.Char(string='N° Document X3', readonly=True)
    request_payload = fields.Text(string='Payload Requête', readonly=True)
    soap_data_sent = fields.Text(string='Données SOAP Envoyées', readonly=True)
    soap_response_raw = fields.Text(string='Réponse SOAP Brute', readonly=True)
    x3_messages = fields.Text(string='Messages X3', readonly=True)
    validation_errors = fields.Text(string='Erreurs Validation', readonly=True)
    duration_ms = fields.Integer(string='Durée (ms)', readonly=True)
    created_at = fields.Datetime(string='Date Création', readonly=True)

    wizard_id = fields.Many2one('sage.x3.log.search.wizard', string='Wizard', ondelete='cascade')

    def action_view_detail(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sage.x3.import.log',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class SageX3LogSearchWizard(models.TransientModel):
    _name = 'sage.x3.log.search.wizard'
    _description = 'Recherche Logs Import Sage X3'
    _inherit = 'sage.x3.mixin'

    reference_document = fields.Char(string='Référence Document')
    date_from = fields.Date(string='Date De')
    date_to = fields.Date(string='Date À')
    log_ids = fields.One2many('sage.x3.import.log', 'wizard_id', string='Logs')
    total_count = fields.Integer(string='Total', readonly=True)
    page = fields.Integer(string='Page', default=1)
    page_size = fields.Integer(string='Taille Page', default=50)

    def action_search(self):
        self.ensure_one()
        config = self._get_sage_x3_config()
        token = self._authenticate_sage_x3()
        if not token:
            raise UserError("Impossible d'obtenir un token Sage X3.")

        params = {'page': self.page, 'pageSize': self.page_size}
        if self.reference_document:
            params['referenceDocument'] = self.reference_document
        if self.date_from:
            params['dateFrom'] = self.date_from.strftime('%Y-%m-%d')
        if self.date_to:
            params['dateTo'] = self.date_to.strftime('%Y-%m-%d')

        logs_url = f"{config['base_url']}/api/ImportLogs"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        try:
            response = self._safe_get(logs_url, headers=headers, params=params)
            data = response.json()
        except Exception as e:
            raise UserError(f"Erreur lors de la récupération des logs : {e}")

        self.log_ids.unlink()

        items = data.get('items', [])

        log_vals = []
        for item in items:
            created_at_raw = item.get('createdAt')
            created_at = None
            if created_at_raw:
                try:
                    created_at = datetime.fromisoformat(created_at_raw.replace('Z', '+00:00')).replace(tzinfo=None)
                except Exception:
                    pass

            status_raw = item.get('status', '')
            status_val = status_raw if status_raw in ('Success', 'Error', 'Warning') else 'Error'

            log_vals.append({
                'wizard_id': self.id,
                'sage_log_id': item.get('id'),
                'import_type': item.get('importType'),
                'import_model': item.get('importModel'),
                'status': status_val,
                'reference_document': item.get('referenceDocument'),
                'x3_document_number': item.get('x3DocumentNumber'),
                'request_payload': item.get('requestPayload'),
                'soap_data_sent': item.get('soapDataSent'),
                'soap_response_raw': item.get('soapResponseRaw'),
                'x3_messages': item.get('x3Messages'),
                'validation_errors': item.get('validationErrors'),
                'duration_ms': item.get('durationMs', 0),
                'created_at': created_at,
            })

        self.env['sage.x3.import.log'].create(log_vals)
        self.total_count = data.get('totalCount', 0)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sage.x3.log.search.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
