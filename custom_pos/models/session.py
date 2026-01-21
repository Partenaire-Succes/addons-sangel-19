import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def check_refund_authorization(self, refund_amount=0.0):
        """
        Vérifie si l'utilisateur actuel a besoin d'un code d'accès pour effectuer un remboursement.
        Les utilisateurs avec group_pos_admin sont exemptés.
        Les utilisateurs group_pos_user uniquement nécessitent un code d'accès.
        
        Args:
            refund_amount: Montant du remboursement (pour information)
        
        Returns:
            Dict avec error, access_required, code_acces, message
        """
        # Si l'utilisateur a group_pos_admin, pas de vérification
        if self.env.user.has_group('custom_pos.group_pos_admin'):
            return {
                'error': False,
                'access_required': False,
                'code_acces': False,
                'message': False,
            }
        
        # Si l'utilisateur n'a même pas group_pos_user, pas de restriction non plus
        if not self.env.user.has_group('custom_pos.group_pos_user'):
            return {
                'error': False,
                'access_required': False,
                'code_acces': False,
                'message': False,
            }
        
        # L'utilisateur est group_pos_user uniquement - code d'accès requis pour remboursement
        pos_config = self.env['pos.config'].search([], limit=1)
        code_acces = pos_config.code_acces if pos_config else False
        
        message = "⚠️ Autorisation requise pour le remboursement.\n\n"
        if refund_amount:
            message += f"Montant à rembourser : {refund_amount:.2f}\n\n"
        message += "Un code d'accès est requis pour effectuer cette opération."
        
        return {
            'error': True,
            'access_required': True,
            'code_acces': code_acces,
            'message': message,
        }

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

    @api.model
    def check_price_reduction(self, order_lines_data):
        """
        Vérifie si un utilisateur groupe_pos_user (uniquement) a réduit le prix d'un produit.
        Les utilisateurs avec des groupes supérieurs (admin, shop, dsi) ne nécessitent pas de code.
        
        Args:
            order_lines_data: Liste de dicts avec {product_id, unit_price}
        
        Returns:
            Dict avec error, access_required, code_acces, message
        """
        # Si l'utilisateur a group_pos_admin ou supérieur, pas de vérification
        if self.env.user.has_group('custom_pos.group_pos_admin'):
            return {
                'error': False,
                'access_required': False,
                'code_acces': False,
                'message': False,
            }
        
        # Si l'utilisateur n'a même pas group_pos_user, pas de restriction
        if not self.env.user.has_group('custom_pos.group_pos_user'):
            return {
                'error': False,
                'access_required': False,
                'code_acces': False,
                'message': False,
            }
        
        # L'utilisateur est group_pos_user uniquement - vérifier les réductions de prix
        reduced_products = []
        for line_data in order_lines_data:
            product = self.env['product.product'].browse(line_data.get('product_id'))
            if product.exists():
                original_price = product.lst_price
                current_price = line_data.get('unit_price', 0)
                if current_price < original_price:
                    reduced_products.append({
                        'name': product.display_name,
                        'original_price': original_price,
                        'new_price': current_price,
                    })
        
        if reduced_products:
            pos_config = self.env['pos.config'].search([], limit=1)
            code_acces = pos_config.code_acces if pos_config else False
            
            product_list = "\n".join(
                f"   • {p['name']}: {p['original_price']:.2f} → {p['new_price']:.2f}"
                for p in reduced_products
            )
            
            return {
                'error': True,
                'access_required': True,
                'code_acces': code_acces,
                'message': f"⚠️ Modification de prix détectée :\n\n{product_list}\n\nUn code d'accès est requis pour valider cette réduction de prix.",
            }
        
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
