import base64
import hashlib
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PosManagerCode(models.Model):
    _name = 'pos.manager.code'
    _inherit = ['pos.load.mixin']
    _description = 'Badge manager POS'
    _order = 'name'

    user_id = fields.Many2one('res.users', 'Manager', required=True, ondelete='cascade')
    name = fields.Char(related='user_id.name', store=True, readonly=True, string='Nom du manager')
    config_id = fields.Many2one('pos.config', 'Caisse de référence', required=True,
                                help="Caisse dont le code d'accès est utilisé pour ce badge.")
    # Stocké directement pour éviter l'accès cross-modèle dans le template QWeb PDF
    badge_code = fields.Char(compute='_compute_badge_code', store=True)
    code_hash = fields.Char(compute='_compute_code_hash', store=True)
    barcode_html = fields.Html(compute='_compute_barcode_html', sanitize=False)
    # Barcode PNG en base64 pour l'impression PDF (évite le chargement URL par wkhtmltopdf)
    badge_barcode_b64 = fields.Char(compute='_compute_badge_barcode_b64', store=False)
    # Logo société en base64 pour l'impression PDF
    logo_b64 = fields.Char(compute='_compute_logo_b64', store=False)
    active = fields.Boolean(default=True)

    @api.depends('config_id.code_acces')
    def _compute_badge_code(self):
        for rec in self:
            rec.badge_code = rec.config_id.code_acces if rec.config_id else False

    def _compute_logo_b64(self):
        for rec in self:
            company = rec.user_id.company_id if rec.user_id else self.env.company
            if company and company.logo:
                rec.logo_b64 = company.logo.decode('utf-8') if isinstance(company.logo, bytes) else company.logo
            else:
                rec.logo_b64 = False

    @api.depends('badge_code')
    def _compute_badge_barcode_b64(self):
        for rec in self:
            if not rec.badge_code:
                rec.badge_barcode_b64 = False
                continue
            # Méthode 1 : API standard Odoo (reportlab via ir.actions.report)
            try:
                barcode_bytes = self.env['ir.actions.report'].barcode(
                    'Code128', rec.badge_code,
                    width=420, height=60, humanreadable=0,
                )
                rec.badge_barcode_b64 = base64.b64encode(barcode_bytes).decode('utf-8')
                continue
            except Exception as e1:
                _logger.warning("Barcode méthode 1 échouée pour %s: %s", rec.name, e1)
            # Méthode 2 : reportlab directement
            try:
                from reportlab.graphics.barcode import createBarcodeDrawing
                drawing = createBarcodeDrawing(
                    'Code128', value=rec.badge_code,
                    width=420, height=60, humanReadable=False,
                )
                rec.badge_barcode_b64 = base64.b64encode(
                    drawing.asString('png')
                ).decode('utf-8')
            except Exception as e2:
                _logger.warning("Barcode méthode 2 échouée pour %s: %s", rec.name, e2)
                rec.badge_barcode_b64 = False

    @api.depends('badge_code')
    def _compute_code_hash(self):
        for rec in self:
            rec.code_hash = (
                hashlib.sha256(rec.badge_code.encode('utf-8')).hexdigest()
                if rec.badge_code else False
            )

    @api.depends('badge_code')
    def _compute_barcode_html(self):
        for rec in self:
            if rec.badge_code:
                rec.barcode_html = (
                    '<div style="text-align:center;margin-top:8px;">'
                    '<img src="/report/barcode/Code128/%s'
                    '?width=420&amp;height=80&amp;humanreadable=0"'
                    ' style="max-width:100%%;height:80px;display:block;margin:0 auto;"/>'
                    '</div>' % rec.badge_code
                )
            else:
                rec.barcode_html = (
                    '<p style="color:#dc3545;padding:8px;">'
                    'Configurez le code d\'accès sur la caisse de référence pour générer le badge.</p>'
                )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [('active', '=', True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'user_id', 'code_hash']

    @api.model
    def validate_manager_code(self, code, action, session_id=None,
                               cashier_name='', order_ref='', price_info=None):
        if not code:
            return {'success': False, 'manager_name': False, 'manager_id': False}

        # Cherche si le code correspond au code_acces d'une caisse
        matching_config = self.env['pos.config'].search([('code_acces', '=', code)], limit=1)
        if matching_config:
            # Tente d'identifier le manager via son badge
            manager = self.search(
                [('active', '=', True), ('badge_code', '=', code)],
                limit=1,
            )
            manager_name = manager.name if manager else 'Manager POS'
            self._write_log(
                manager_code=manager if manager else None,
                manager_name=manager_name,
                action=action,
                session_id=session_id,
                cashier_name=cashier_name,
                order_ref=order_ref,
                offline=False,
                price_info=price_info,
            )
            return {
                'success': True,
                'manager_name': manager_name,
                'manager_id': manager.id if manager else False,
            }

        return {'success': False, 'manager_name': False, 'manager_id': False}

    def _write_log(self, manager_code, manager_name, action,
                   session_id, cashier_name, order_ref, offline=False, price_info=None):
        session = (
            self.env['pos.session'].browse(session_id)
            if session_id else self.env['pos.session']
        )
        pos_config = (
            session.config_id
            if session.exists() else self.env['pos.config'].search([], limit=1)
        )
        vals = {
            'manager_code_id': manager_code.id if manager_code else False,
            'manager_name': manager_name or '',
            'action': action or 'unknown',
            'session_id': session.id if session.exists() else False,
            'config_id': pos_config.id if pos_config else False,
            'company_id': pos_config.company_id.id if pos_config and pos_config.company_id else False,
            'cashier_name': cashier_name or '',
            'order_ref': order_ref or '',
            'offline': offline,
        }
        if price_info and isinstance(price_info, dict):
            vals['old_price'] = float(price_info.get('old_price') or 0.0)
            vals['new_price'] = float(price_info.get('new_price') or 0.0)
            vals['price_product'] = str(price_info.get('product_name') or '')
        self.env['pos.access.log'].sudo().create(vals)

    def action_print_badge(self):
        return self.env.ref('custom_pos.action_report_manager_badge').report_action(self)


class PosAccessLog(models.Model):
    _name = 'pos.access.log'
    _description = 'Journal des validations POS'
    _order = 'datetime desc'

    datetime = fields.Datetime('Date/Heure', default=fields.Datetime.now, readonly=True)
    company_id = fields.Many2one('res.company', 'Magasin', readonly=True)
    config_id = fields.Many2one('pos.config', 'Caisse', readonly=True)
    session_id = fields.Many2one('pos.session', 'Session', readonly=True)
    cashier_name = fields.Char('Caissière', readonly=True)
    manager_code_id = fields.Many2one(
        'pos.manager.code', 'Badge', readonly=True, ondelete='set null'
    )
    manager_name = fields.Char('Validé par', readonly=True)
    action = fields.Selection([
        ('refund', 'Remboursement'),
        ('discount', 'Remise manuelle'),
        ('stock', 'Rupture de stock'),
        ('price_reduction', 'Réduction de prix'),
        ('print', 'Impression ticket'),
        ('details', 'Détails commande'),
        ('invoice', 'Facture'),
        ('unknown', 'Autre'),
    ], string='Action validée', readonly=True)
    order_ref = fields.Char('Référence commande', readonly=True)
    offline = fields.Boolean('Hors-ligne', readonly=True, default=False)
    price_product = fields.Char('Produit(s) modifié(s)', readonly=True)
    old_price = fields.Float('Ancien prix', readonly=True, digits='Product Price')
    new_price = fields.Float('Nouveau prix', readonly=True, digits='Product Price')
