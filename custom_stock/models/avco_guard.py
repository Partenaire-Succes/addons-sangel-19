# -*- coding: utf-8 -*-
"""
Garde-fou AVCO — Detecte les couts aberrants et alerte avant qu'ils impactent
les rapports et la comptabilite.

Regles de sante AVCO :
  1. standard_price < 0              → toujours aberrant
  2. standard_price = 0 AND stock > 0 → produit en stock sans cout
  3. standard_price > SEUIL_MAX      → valeur improbable (configurable)

Le cron tourne chaque nuit et poste un message dans le chatter de chaque
produit corrompu + envoie un mail a l'administrateur.
"""
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)

SEUIL_MAX_FCFA = 10_000_000  # 10 millions FCFA — ajuster selon votre catalogue


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _cron_check_avco_sanity(self):
        """Detecte les produits AVCO avec un cout aberrant."""
        companies = self.env['res.company'].search([])
        all_corrupted = []

        for company in companies:
            products = self.with_company(company).search([
                ('type', '=', 'product'),
                ('categ_id.property_cost_method', 'in', ['average', 'fifo']),
            ])

            for product in products:
                price = product.with_company(company).standard_price
                qty = product.with_context(company_id=company.id).qty_available

                reasons = []
                if price < 0:
                    reasons.append(f'Cout negatif : {price:.2f} FCFA')
                if price == 0.0 and qty > 0:
                    reasons.append(f'Cout nul mais stock = {qty}')
                if price > SEUIL_MAX_FCFA:
                    reasons.append(f'Cout anormalement eleve : {price:,.0f} FCFA')

                if reasons:
                    all_corrupted.append({
                        'product': product,
                        'company': company,
                        'reasons': reasons,
                        'price': price,
                        'qty': qty,
                    })
                    _logger.error(
                        '[AVCO_GUARD] %s (id=%s) societe=%s — %s',
                        product.display_name, product.id, company.name,
                        ' | '.join(reasons),
                    )

        if all_corrupted:
            self._avco_guard_notify(all_corrupted)

        return True

    @api.model
    def _avco_guard_notify(self, corrupted_list):
        """Envoie un mail d'alerte et poste dans le chatter de chaque produit."""
        # -- Chatter sur chaque produit --
        for item in corrupted_list:
            try:
                item['product'].message_post(
                    body=(
                        '<b>ALERTE AVCO</b> : Cout aberrant detecte par le garde-fou.<br/>'
                        + '<br/>'.join(item['reasons'])
                        + '<br/><i>Verifiez la couche de valorisation (stock.valuation.layer) '
                        'de cet article.</i>'
                    ),
                    subject='ALERTE : Cout AVCO aberrant',
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            except Exception as e:
                _logger.error('[AVCO_GUARD] Impossible de poster le chatter : %s', e)

        # -- Email a l'administrateur --
        try:
            admin = self.env.ref('base.user_admin', raise_if_not_found=False)
            if not admin or not admin.email:
                return

            lines_html = ''.join(
                '<tr><td>{name}</td><td>{company}</td>'
                '<td style="color:red">{price:,.0f}</td>'
                '<td>{qty}</td><td>{reasons}</td></tr>'.format(
                    name=item['product'].display_name,
                    company=item['company'].name,
                    price=item['price'],
                    qty=item['qty'],
                    reasons=' | '.join(item['reasons']),
                )
                for item in corrupted_list
            )
            body = (
                '<p>Le garde-fou AVCO a detecte <b>{count}</b> produit(s) '
                'avec un cout aberrant :</p>'
                '<table border="1" cellpadding="4" cellspacing="0">'
                '<tr><th>Article</th><th>Societe</th><th>Cout actuel (FCFA)</th>'
                '<th>Stock</th><th>Probleme</th></tr>'
                '{lines}'
                '</table>'
                '<p><b>Action requise :</b> verifiez stock.valuation.layer pour '
                'chaque article liste ci-dessus et corrigez le cout via '
                'Inventaire &rarr; Mise a jour du prix standard.</p>'
            ).format(count=len(corrupted_list), lines=lines_html)

            self.env['mail.mail'].create({
                'subject': f'[ALERTE AVCO] {len(corrupted_list)} produit(s) avec cout aberrant',
                'email_to': admin.email,
                'body_html': body,
                'auto_delete': True,
            }).send()

        except Exception as e:
            _logger.error('[AVCO_GUARD] Impossible d\'envoyer le mail d\'alerte : %s', e)
