from odoo import http
from odoo.http import request

class PosPromoController(http.Controller):

    @http.route('/pos_promo/check_3x4', type='json', auth='user', csrf=False)
    def check_3x4(self, product_id, qty, lot_lines=None):
        try:
            result = request.env['pos.order'].sudo().check_promo_3x4(
                product_id=product_id,
                qty=qty,
                lot_lines=lot_lines or []
            )
            return result
        except Exception as e:
            return {'apply': False, 'reason': 'server_exception', 'message': str(e)}
