import base64
import hashlib
import io
import json
import logging
from odoo import models, fields, api, exceptions

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
    badge_code = fields.Char(compute='_compute_badge_code', store=True)
    code_hash = fields.Char(compute='_compute_code_hash', store=True)
    barcode_html = fields.Html(compute='_compute_barcode_html', sanitize=False)
    badge_barcode_b64 = fields.Char(compute='_compute_badge_barcode_b64', store=False)
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
            try:
                barcode_bytes = self.env['ir.actions.report'].barcode(
                    'Code128', rec.badge_code,
                    width=420, height=60, humanreadable=0,
                )
                rec.badge_barcode_b64 = base64.b64encode(barcode_bytes).decode('utf-8')
                continue
            except Exception as e1:
                _logger.warning("Barcode méthode 1 échouée pour %s: %s", rec.name, e1)
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
                               cashier_name='', order_ref='', price_info=None,
                               create_log=True):
        if not code:
            return {'success': False, 'manager_name': False, 'manager_id': False}

        matching_config = self.env['pos.config'].search([('code_acces', '=', code)], limit=1)
        if matching_config:
            manager = self.search(
                [('active', '=', True), ('badge_code', '=', code)],
                limit=1,
            )
            manager_name = manager.name if manager else 'Manager POS'
            if create_log:
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

    @api.model
    def create_deferred_logs(self, pending_logs, session_id=None, cashier_name='', order_ref=''):
        """Crée les logs différés après finalisation du ticket (référence disponible)."""
        for entry in (pending_logs or []):
            manager_id = entry.get('manager_id')
            manager = self.browse(int(manager_id)) if manager_id else self.browse()
            if manager and not manager.exists():
                manager = self.browse()
            manager_name = manager.name if manager else 'Manager POS'
            self._write_log(
                manager_code=manager if manager else None,
                manager_name=manager_name,
                action=entry.get('action', 'unknown'),
                session_id=session_id,
                cashier_name=cashier_name,
                order_ref=order_ref,
                offline=False,
                price_info=entry.get('price_info'),
            )
        return True

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
        if price_info:
            if isinstance(price_info, list):
                vals['price_details'] = json.dumps(price_info, ensure_ascii=False)
            elif isinstance(price_info, dict):
                vals['price_details'] = json.dumps([{
                    'produit': str(price_info.get('product_name') or ''),
                    'avant': float(price_info.get('old_price') or 0.0),
                    'apres': float(price_info.get('new_price') or 0.0),
                }], ensure_ascii=False)
        self.env['pos.access.log'].sudo().create(vals)

    def action_print_badge(self):
        return self.env.ref('custom_pos.action_report_manager_badge').report_action(self)

    def action_download_badge_jpeg(self):
        """Télécharge le badge au format JPEG 502×325px."""
        self.ensure_one()
        if not self.badge_code:
            raise exceptions.UserError(
                "Ce badge n'a pas de code configuré. "
                "Définissez le code d'accès sur la caisse de référence."
            )
        jpeg_bytes = self._render_badge_as_jpeg()
        filename = "Badge_POS_%s.jpg" % self.name.replace(' ', '_')
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': base64.b64encode(jpeg_bytes).decode('utf-8'),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'image/jpeg',
            'type': 'binary',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'new',
        }

    def _render_badge_as_jpeg(self):
        """
        Génère le badge JPEG 502×325px.
        Méthode 1 : pdf2image (pip install pdf2image + poppler) — rendu identique au PDF.
        Méthode 2 : reconstruction Pillow (toujours disponible dans Odoo).
        """
        # ── Méthode 1 : pdf2image ────────────────────────────────────────────
        try:
            from pdf2image import convert_from_bytes
            report = self.env.ref('custom_pos.action_report_manager_badge')
            pdf_bytes = report._render_qweb_pdf(self.ids)[0]
            pages = convert_from_bytes(pdf_bytes, dpi=150, first_page=1, last_page=1)
            buf = io.BytesIO()
            pages[0].save(buf, 'JPEG', quality=95)
            return buf.getvalue()
        except Exception as e:
            _logger.info("pdf2image indisponible, fallback Pillow: %s", e)

        # ── Méthode 2 : Pillow ───────────────────────────────────────────────
        return self._render_badge_pillow()

    def _render_badge_pillow(self):
        """Reconstruction pixel-perfect du badge avec Pillow uniquement."""
        from PIL import Image, ImageDraw, ImageFont

        W, H = 502, 319
        BLUE = (85, 121, 172)    # #5579ac
        WHITE = (255, 255, 255)

        # Hauteurs proportionnelles : header 9mm / body 33mm / footer 7mm sur 49mm
        HEADER_H = round(9 / 49 * H)       # ≈ 59px
        FOOTER_H = round(7 / 49 * H)       # ≈ 46px
        BODY_H = H - HEADER_H - FOOTER_H   # ≈ 220px

        img = Image.new('RGB', (W, H), WHITE)
        draw = ImageDraw.Draw(img)

        # Zones colorées
        draw.rectangle([0, 0, W, HEADER_H], fill=BLUE)
        draw.rectangle([0, H - FOOTER_H, W, H], fill=BLUE)
        draw.rectangle([0, 0, W - 1, H - 1], outline=BLUE, width=2)

        def _font(size, bold=False):
            candidates = (
                ['/Library/Fonts/Arial Bold.ttf',
                 '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
                if bold else
                ['/Library/Fonts/Arial.ttf',
                 '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
            )
            for path in candidates:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        # Logo (header gauche)
        logo_right = 8
        if self.logo_b64:
            try:
                logo_img = Image.open(io.BytesIO(base64.b64decode(self.logo_b64))).convert('RGBA')
                max_h = HEADER_H - 10
                logo_img.thumbnail((max_h, max_h), Image.LANCZOS)
                bg = Image.new('RGB', logo_img.size, BLUE)
                bg.paste(logo_img, mask=logo_img.split()[3])
                img.paste(bg, (8, (HEADER_H - bg.height) // 2))
                logo_right = 8 + bg.width + 6
            except Exception as e:
                _logger.warning("Badge JPEG logo: %s", e)

        # Header : nom société + libellé droit
        company_name = (self.user_id.company_id.name or '').upper()
        draw.text((logo_right, HEADER_H // 2), company_name,
                  fill=WHITE, font=_font(11, bold=True), anchor='lm')
        draw.text((W - 8, HEADER_H // 2), 'BADGE MANAGER POS',
                  fill=WHITE, font=_font(9), anchor='rm')

        # Corps : nom du manager + rôle
        name_y = HEADER_H + BODY_H // 4
        draw.text((W // 2, name_y), self.name or '',
                  fill=BLUE, font=_font(22, bold=True), anchor='mm')
        draw.text((W // 2, name_y + 32), 'VALIDATEUR POS - TOUTES CAISSES',
                  fill=BLUE, font=_font(9), anchor='mm')

        # Code-barres
        if self.badge_barcode_b64:
            try:
                bc_img = Image.open(io.BytesIO(base64.b64decode(self.badge_barcode_b64))).convert('RGB')
                bc_w, bc_h = W - 40, 50
                bc_img = bc_img.resize((bc_w, bc_h), Image.LANCZOS)
                img.paste(bc_img, ((W - bc_w) // 2, HEADER_H + BODY_H - bc_h - 8))
            except Exception as e:
                _logger.warning("Badge JPEG barcode: %s", e)

        # Footer
        draw.text((W // 2, H - FOOTER_H // 2),
                  'CONFIDENTIEL - Badge nominatif - Ne pas reproduire',
                  fill=WHITE, font=_font(9), anchor='mm')

        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=95)
        return buf.getvalue()


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
    price_details = fields.Text(
        'Détails produits', readonly=True,
        help="JSON : liste de {produit, avant, apres} — une entrée par produit affecté."
    )
    price_details_formatted = fields.Char(
        'Produits modifiés', compute='_compute_price_details_formatted', store=False
    )

    @api.depends('price_details')
    def _compute_price_details_formatted(self):
        for rec in self:
            if not rec.price_details:
                rec.price_details_formatted = ''
                continue
            try:
                data = json.loads(rec.price_details)
                parts = []
                for item in data:
                    produit = item.get('produit', '?')
                    avant = item.get('avant')
                    apres = item.get('apres')
                    if avant is not None and apres is not None:
                        parts.append(f"{produit}: {avant:.0f} → {apres:.0f}")
                    else:
                        parts.append(produit)
                rec.price_details_formatted = ' | '.join(parts)
            except Exception:
                rec.price_details_formatted = rec.price_details or ''
