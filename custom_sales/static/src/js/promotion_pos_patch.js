/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

/**
 * Promotion POS patch (sale.promotion)
 *
 * Applique automatiquement la remise promotionnelle sur les produits en caisse.
 *
 * Conditions d'application :
 * - La promotion a apply_in_pos = true et active = true
 * - La date du jour est comprise entre date_start et date_end de la promotion
 * - La date du jour est comprise entre date_start et date_end de la ligne produit
 * - Le produit de la ligne de commande correspond au product_id de la ligne de promo
 *
 * Priorité : on prend la remise la plus haute entre la remise globale (partenaire)
 * et la remise promotionnelle. Les deux ne se cumulent pas.
 */

/**
 * Vérifie si une date string (YYYY-MM-DD) est valide et renvoie un objet Date à minuit.
 */
function toMidnight(dateStr) {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    d.setHours(0, 0, 0, 0);
    return d;
}

/**
 * Retourne la remise promo active (en %) pour un produit donné,
 * en parcourant tous les modèles sale.promotion et sale.promotion.line chargés.
 *
 * @param {Object} models - this.models du PosStore (registre des modèles POS)
 * @param {number} productId - ID du product.product
 * @returns {number} - Remise en % (0 si aucune promo active)
 */
function getPromotionDiscount(models, productId) {
    if (!productId || !models['sale.promotion'] || !models['sale.promotion.line']) {
        return 0;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Récupère toutes les lignes de promo chargées
    const promoLines = models['sale.promotion.line'].getAll();
    if (!promoLines || promoLines.length === 0) {
        return 0;
    }

    let bestDiscount = 0;

    for (const line of promoLines) {
        // Résolution de l'ID produit (peut être un objet record ou un entier)
        const lineProductId = line.product_id && typeof line.product_id === 'object'
            ? line.product_id.id
            : line.product_id;

        if (lineProductId !== productId) {
            continue;
        }

        // Vérifie la période de validité de la ligne
        const lineStart = toMidnight(line.date_start);
        const lineEnd = toMidnight(line.date_end);

        if (lineStart && lineStart > today) continue;
        if (lineEnd && lineEnd < today) continue;

        // Vérifie que la promotion parente est elle-même dans sa période
        const promo = line.promotion_id && typeof line.promotion_id === 'object'
            ? line.promotion_id
            : models['sale.promotion'].get(line.promotion_id);

        if (!promo) continue;

        const promoStart = toMidnight(promo.date_start);
        const promoEnd = toMidnight(promo.date_end);

        if (promoStart && promoStart > today) continue;
        if (promoEnd && promoEnd < today) continue;

        if (line.discount > bestDiscount) {
            bestDiscount = line.discount;
        }
    }

    return bestDiscount;
}

/**
 * Patch PosOrderline pour permettre la fusion de lignes avec remise promo,
 * identique au comportement existant pour la remise globale partenaire.
 */
patch(PosOrderline.prototype, {
    canBeMergedWith(orderline) {
        const thisHasPromoDiscount = this._promoDiscountApplied === true;
        const otherHasPromoDiscount = orderline._promoDiscountApplied === true;
        const thisHasGlobalDiscount = this._globalDiscountApplied === true;
        const otherHasGlobalDiscount = orderline._globalDiscountApplied === true;
        const thisHasAutoDiscount = thisHasPromoDiscount || thisHasGlobalDiscount;
        const otherHasAutoDiscount = otherHasPromoDiscount || otherHasGlobalDiscount;

        if (thisHasAutoDiscount && otherHasAutoDiscount && thisHasPromoDiscount) {
            const originalDiscount = this.discount;
            this.discount = 0;
            const canMerge = super.canBeMergedWith(orderline);
            this.discount = originalDiscount;
            return canMerge;
        }

        return super.canBeMergedWith(orderline);
    },
});

/**
 * Patch PosOrder.setPartner : si le nouveau partenaire est exclu des promotions,
 * on retire les remises promo des lignes existantes AVANT que la remise globale
 * ne soit recalculée (le super déclenche global_discount_patch qui réapplique la
 * remise partenaire si elle est configurée).
 */
patch(PosOrder.prototype, {
    setPartner(partner) {
        if (partner && partner.no_promotion && this.lines) {
            for (const line of this.lines) {
                if (line._promoDiscountApplied) {
                    line._promoDiscountApplied = false;
                    line.setDiscount(0);
                }
            }
        }
        super.setPartner(partner);
    },
});

/**
 * Patch PosStore.addLineToOrder pour appliquer la remise promo après ajout de ligne.
 * Prend la remise la plus haute entre remise globale partenaire et remise promo.
 */
patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        const result = await super.addLineToOrder(vals, order, opts, configure);

        if (order) {
            // Ne pas appliquer si le partenaire est exclu des promotions
            const partner = order.get_partner ? order.get_partner() : order.partner_id;
            if (partner && partner.no_promotion) {
                return result;
            }

            const selectedLine = order.getSelectedOrderline();
            if (selectedLine && selectedLine.product_id) {
                const productId = selectedLine.product_id.id || selectedLine.product_id;
                const promoDiscount = getPromotionDiscount(this.models, productId);

                if (promoDiscount > 0) {
                    const currentDiscount = selectedLine.getDiscount() || 0;

                    // Applique uniquement si la remise promo est plus haute
                    if (promoDiscount > currentDiscount) {
                        selectedLine.setDiscount(promoDiscount);
                        selectedLine._promoDiscountApplied = true;
                        // Si la remise globale était appliquée et est plus faible, on la remplace
                        if (selectedLine._globalDiscountApplied) {
                            selectedLine._globalDiscountApplied = false;
                        }
                        order.recomputeOrderData();
                    }
                }
            }
        }

        return result;
    },
});
