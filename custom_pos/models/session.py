import logging

from odoo import api, fields, models

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

    prelevement_number = fields.Char(
        string="Numéro de prélèvement",
        copy=False,
        readonly=True,
        help="Numéro de séquence pour le ticket de prélèvement"
    )

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        # Ajouter code_article de product.template aux champs chargés
        result['search_params']['fields'].append('product_tmpl_id.code_article')
        return result

    def _get_prelevement_number(self):
        """Generate or return the prelevement sequence number for this session"""
        self.ensure_one()
        if not self.prelevement_number:
            sequence = self.env['ir.sequence'].next_by_code('prelevement.ticket')
            self.prelevement_number = sequence
        return self.prelevement_number

    def _get_prelevement_payment_data(self):
        """
        Get payment data for the prelevement ticket:
        - cash_total: Total amount of cash payments
        - titre_payments: List of individual payments with titre_paiement payment methods
        """
        self.ensure_one()
        
        # Get all payments for this session
        payments = self.env['pos.payment'].search([
            ('session_id', '=', self.id),
        ])
        
        cash_total = 0.0
        titre_payments = []
        
        for payment in payments:
            payment_method = payment.payment_method_id
            
            # Cash payments (Espèces)
            if payment_method.is_cash_count:
                cash_total += payment.amount
            
            # Titre de paiement payments - each individual transaction
            elif payment_method.is_titre_paiement:
                titre_payments.append({
                    'method_name': payment_method.name,
                    'amount': payment.amount,
                    'cashier_name': payment.session_id.user_id.name,
                })
        
        return {
            'cash_total': cash_total,
            'titre_payments': titre_payments,
        }

    def action_print_prelevement_ticket(self):
        """Action to print the prelevement ticket"""
        self.ensure_one()
        return self.env.ref('custom_pos.action_report_prelevement_ticket').report_action(self)

    def save_cash_count_for_prelevement(self, counted_cash):
        """
        Save the counted cash amount to the session before printing the prelevement ticket.
        This is called from the MoneyDetailsPopup JS when user confirms the cash count.
        The value needs to be saved first so the report template can read it.
        
        Args:
            counted_cash: The total cash amount entered by the user
        
        Returns:
            dict with success status and session_id
        """
        self.ensure_one()
        self.cash_register_balance_end_real = counted_cash
        return {
            'success': True,
            'session_id': self.id,
            'counted_cash': counted_cash,
        }

    def _get_cloture_caisse_data(self):
        """
        Get data for the "Cloture de caisse" report.
        Section 1: Ventes en compte (Glovo/Yango payments)
        Section 2: Fond de caisse initial (opening drawer contents)
        Section 3: Encaissements comptants (cash receipts by payment type)
        """
        self.ensure_one()
        
        # ============================================
        # SECTION 1: Ventes en compte (En cours / Compte client)
        # ============================================
        # Using is_limit field from custom_food_credit module
        ventes_en_compte_payments = self.env['pos.payment'].search([
            ('session_id', '=', self.id),
            ('payment_method_id.is_limit', '=', True),
        ])
        
        ventes_en_compte = {
            'count': len(ventes_en_compte_payments),
            'total': sum(ventes_en_compte_payments.mapped('amount')),
        }
        
        # ============================================
        # SECTION 2: Fond de caisse initial
        # ============================================
        # Espèces: Initial cash amount when POS was opened
        # Chèques, Cartes, Titres: Always 0 (not part of initial drawer)
        fond_de_caisse_initial = {
            'especes': self.cash_register_balance_start or 0.0,
            'cheques': 0.0,
            'cartes': 0.0,
            'titres_paiements': 0.0,
        }
        
        # ============================================
        # SECTION 3: Encaissements comptants
        # ============================================
        # Get all payments for this session
        all_payments = self.env['pos.payment'].search([
            ('session_id', '=', self.id),
        ])
        
        # Espèces (Cash) - using is_cash_count
        especes_payments = all_payments.filtered(lambda p: p.payment_method_id.is_cash_count)
        especes = {
            'count': len(especes_payments),
            'total': sum(especes_payments.mapped('amount')),
        }
        
        # Chèques - using is_cheque
        cheques_payments = all_payments.filtered(lambda p: p.payment_method_id.is_cheque)
        cheques = {
            'count': len(cheques_payments),
            'total': sum(cheques_payments.mapped('amount')),
        }
        
        # Cartes (Bank cards) - using is_bank_card
        cartes_payments = all_payments.filtered(lambda p: p.payment_method_id.is_bank_card)
        cartes = {
            'count': len(cartes_payments),
            'total': sum(cartes_payments.mapped('amount')),
        }
        
        # Avoir (Credit/Loyalty) - using is_loyalty OR is_food
        avoir_payments = all_payments.filtered(
            lambda p: p.payment_method_id.is_loyalty or p.payment_method_id.is_food
        )
        avoir = {
            'count': len(avoir_payments),
            'total': sum(avoir_payments.mapped('amount')),
        }
        
        # Titre de paiements - using is_titre_paiement
        titres_payments = all_payments.filtered(lambda p: p.payment_method_id.is_titre_paiement)
        titres = {
            'count': len(titres_payments),
            'total': sum(titres_payments.mapped('amount')),
        }
        
        # Total encaissements comptants
        total_encaissements = {
            'count': especes['count'] + cheques['count'] + cartes['count'] + avoir['count'] + titres['count'],
            'total': especes['total'] + cheques['total'] + cartes['total'] + avoir['total'] + titres['total'],
        }
        
        encaissements_comptants = {
            'especes': especes,
            'cheques': cheques,
            'cartes': cartes,
            'avoir': avoir,
            'titres': titres,
            'total': total_encaissements,
        }
        
        # ============================================
        # SECTION 4: Prélèvements (user's counted amounts)
        # ============================================
        # Espèces: What user entered as cash count at closing (Nbre=1 by default)
        prelevements_especes = {
            'count': 1,
            'total': self.cash_register_balance_end_real or 0.0,
        }
        
        # Chèques, Cartes, Titres: Same as encaissements (not recounted physically)
        prelevements_cheques = cheques.copy()
        prelevements_cartes = cartes.copy()
        prelevements_titres = titres.copy()
        
        # Total prélèvements
        total_prelevements = {
            'count': prelevements_especes['count'] + prelevements_cheques['count'] + prelevements_cartes['count'] + prelevements_titres['count'],
            'total': prelevements_especes['total'] + prelevements_cheques['total'] + prelevements_cartes['total'] + prelevements_titres['total'],
        }
        
        prelevements = {
            'especes': prelevements_especes,
            'cheques': prelevements_cheques,
            'cartes': prelevements_cartes,
            'titres': prelevements_titres,
            'total': total_prelevements,
        }
        
        return {
            'ventes_en_compte': ventes_en_compte,
            'fond_de_caisse_initial': fond_de_caisse_initial,
            'encaissements_comptants': encaissements_comptants,
            'prelevements': prelevements,
        }

    def action_print_cloture_caisse(self):
        """Action to print the cloture de caisse ticket"""
        self.ensure_one()
        return self.env.ref('custom_pos.action_report_cloture_caisse').report_action(self)
