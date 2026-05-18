# -*- coding: utf-8 -*-
"""
Garde-fou AVCO — deux niveaux de protection :

  NIVEAU 1 — Prevention (temps reel)
    Override de _update_standard_price : si le nouveau cout est plus de 1000x
    superieur a l'ancien (artefact flottant par division quasi-zero), le prix
    est bloque et l'ancien cout est conserve.

    Cause racine : -0.02 + 0.02 = 5.55e-18 en IEEE 754 (pas exactement 0).
    Odoo calcule alors AVCO = valeur / 5.55e-18 = 1.54e+16.

  NIVEAU 2 — Detection (cron nocturne)
    Scanne tous les produits AVCO et alerte si un cout aberrant passe quand meme.
"""
import logging
from odoo import api, models
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

SEUIL_MAX_FCFA   = 10_000_000   # 10 millions FCFA — ajuster selon catalogue
RATIO_ALERTE     = 1_000        # prix_nouveau > prix_ancien * 1000 → corruption FP


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # -------------------------------------------------------------------------
    # NIVEAU 1 : Prevention en temps reel
    # -------------------------------------------------------------------------

    def _update_standard_price(self, extra_value=None, extra_quantity=None):
        """
        Protege contre la corruption AVCO par division par quasi-zero.

        Quand le stock passe par zero apres une vente negative + ajustement
        d'inventaire, la quantite resultante est 5.55e-18 (IEEE 754) au lieu
        de 0.0 exactement. Odoo divise la valeur par ce flottant et obtient
        un prix absurde (ex : 1.54e+16 FCFA).

        Ce garde-fou compare le nouveau prix avec l'ancien : si le rapport
        depasse RATIO_ALERTE et que la quantite disponible est quasi-nulle,
        on bloque la mise a jour et on conserve le dernier prix valide.
        """
        # Sauvegarder les prix avant mise a jour
        prix_avant = {
            p.id: p.with_company(self.env.company).standard_price
            for p in self
            if p.cost_method == 'average'
        }

        result = super()._update_standard_price(
            extra_value=extra_value,
            extra_quantity=extra_quantity,
        )

        # Verifier chaque produit AVCO apres mise a jour
        for product in self:
            if product.cost_method != 'average':
                continue
            ancien  = prix_avant.get(product.id, 0.0)
            nouveau = product.with_company(self.env.company).standard_price

            qty_dispo = product.with_context(company_id=self.env.company.id).qty_available
            qty_nulle = float_is_zero(qty_dispo, precision_rounding=product.uom_id.rounding)

            # --- Detection par valeur absolue -----------------------------------
            # L'ancienne logique utilisait (nouveau > ancien * RATIO_ALERTE)
            # et sautait si nouveau <= 0. Cela manquait les corruptions negatives
            # (ex : -2.22e22) car la condition `nouveau <= 0` stoppait le check.
            #
            # On utilise abs(nouveau) pour capter les deux sens de corruption :
            #   + infini (valeur residuelle positive / quasi-zero)
            #   - infini (valeur residuelle negative / quasi-zero)
            # -----------------------------------------------------------------------
            abs_nouveau = abs(nouveau)

            corruption_detectee = (
                # Cas 1 : valeur absolue depasse le seuil physique max — stock nul
                (abs_nouveau > SEUIL_MAX_FCFA and qty_nulle)
                # Cas 2 : rapport vs ancien trop grand — stock nul — si ancien connu
                or (ancien > 0 and abs_nouveau > ancien * RATIO_ALERTE and qty_nulle)
            )

            if not corruption_detectee:
                continue

            # Prix de repli : dernier prix valide avant le mouvement (ou 0 si inconnu)
            prix_repli = ancien if ancien > 0 else 0.0

            _logger.warning(
                '[AVCO_GUARD] Corruption FP bloquee — produit: %s (id=%s) '
                'ancien: %.4f  nouveau aberrant: %.4e  qty: %.6f — '
                'Prix restaure: %.4f',
                product.display_name, product.id, ancien, nouveau,
                qty_dispo, prix_repli,
            )
            product.sudo().with_context(
                disable_auto_revaluation=True
            ).standard_price = prix_repli

            try:
                product.message_post(
                    body=(
                        '<b>AVCO GUARD</b> : Corruption de prix bloquee automatiquement.<br/>'
                        f'Prix aberrant calcule : <b>{nouveau:,.2f} FCFA</b><br/>'
                        f'Prix restaure : <b>{prix_repli:,.2f} FCFA</b><br/>'
                        f'Quantite en stock : <b>{qty_dispo:.4f}</b><br/>'
                        '<i>Cause : stock passe par zero (vente en negatif + '
                        'ajustement inventaire). Valeur residuelle non nulle '
                        'divisee par une quantite quasi-zero (IEEE 754).</i>'
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
            except Exception as exc:
                _logger.error('[AVCO_GUARD] Impossible de poster le chatter : %s', exc)

        return result

    # -------------------------------------------------------------------------
    # NIVEAU 2 : Detection nocturne (cron)
    # -------------------------------------------------------------------------

    @api.model
    def _cron_check_avco_sanity(self):
        """Detecte les produits AVCO avec un cout aberrant (filet de securite)."""
        companies = self.env['res.company'].search([])
        all_corrupted = []

        for company in companies:
            products = self.with_company(company).search([
                ('type', '=', 'product'),
                ('categ_id.property_cost_method', 'in', ['average', 'fifo']),
            ])

            for product in products:
                price = product.with_company(company).standard_price
                qty   = product.with_context(company_id=company.id).qty_available

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
                        'price':   price,
                        'qty':     qty,
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
            except Exception as exc:
                _logger.error('[AVCO_GUARD] Impossible de poster le chatter : %s', exc)

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

        except Exception as exc:
            _logger.error('[AVCO_GUARD] Impossible d\'envoyer le mail d\'alerte : %s', exc)
