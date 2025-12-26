import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = "pos.order"


    @api.model
    def check_stock_levels(self, product_ids, has_discount=False):
        produits_rupture = []
        products = self.env['product.product'].browse(product_ids)

        # Si l'utilisateur est admin, pas de vérification
        if self.env.user.has_group('custom_pos.group_pos_admin'):
            return {
                'error': False,
                'access_required': False,
                'code_acces': False,
                'message': False,
            }

        # Vérification du stock
        for product in products:
            if product.qty_available <= 0:
                produits_rupture.append(product.display_name)

        pos_config = self.env['pos.config'].search([], limit=1)
        code_acces = pos_config.code_acces if pos_config else False

        # Si rupture de stock ET remise
        if produits_rupture and has_discount:
            return {
                'error': True,
                'access_required': True,
                'code_acces': code_acces,
                'message': "⚠️ Autorisation requise :\n\n" +
                        "Produits en rupture de stock :\n" +
                        "\n".join(f"   • {p}" for p in produits_rupture),
            }

        # Si seulement rupture de stock
        if produits_rupture:
            return {
                'error': True,
                'access_required': True,
                'code_acces': code_acces,
                'message': "Les produits suivants sont en rupture de stock :\n" +
                        "\n".join(produits_rupture),
            }

        # Si seulement remise
        if has_discount:
            return {
                'error': True,
                'access_required': True,
                'code_acces': code_acces,
                'message': "⚠️ Cette commande contient des remises.\nUn code d'accès est requis pour continuer.",
            }

        # Tout est OK
        return {
            'error': False,
            'access_required': False,
            'code_acces': False,
            'message': False,
        }

    
    def _export_for_receipt(self):
        """Ajouter le nom de la caisse aux données du reçu"""
        result = super(PosOrder, self)._export_for_receipt()
        result['pos_config_name'] = self.config_id.name
        return result


    @api.model
    def check_promo_3x4(self, product_id, qty, lot_lines=None):
        Product = self.env['product.product'].browse(product_id)
        if not Product.exists():
            return {'apply': False, 'reason': 'product_not_found'}

        # Optionnel : champ produit
        is_promo = getattr(Product, 'is_promo_3x4', True)
        if not is_promo:
            return {'apply': False, 'reason': 'product_not_eligible'}

        # Si produit tracé par lot/série
        if lot_lines:
            computed_qty = 0
            for lot in lot_lines:
                computed_qty += lot.get('qty') or 1
            qty = computed_qty

        qty = int(qty or 0)
        if qty < 3:
            return {'apply': False, 'reason': 'qty_too_low', 'qty': qty}

        free_qty = qty // 3
        discount_amount = free_qty * Product.lst_price

        return {
            'apply': True,
            'free_qty': free_qty,
            'discount_amount': discount_amount,
            'qty': qty,
        }
    

class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        # Ajouter code_article de product.template aux champs chargés
        result['search_params']['fields'].append('product_tmpl_id.code_article')
        return result


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    def _load_pos_data_fields(self, config_id):
        """Ajouter le champ is_loyalty aux données chargées dans le POS"""
        fields = super()._load_pos_data_fields(config_id)
        fields.append('is_loyalty')
        return fields
