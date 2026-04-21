/** @odoo-module */

import { Order, Orderline } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

/**
 * Retourne les IDs des taxes AIRSI d'un produit disponibles dans le POS.
 * @param {Object} product - produit POS
 * @param {Object} models - registre des modèles POS
 * @returns {Array} liste des taxes AIRSI
 */
function getProductAirsiTaxes(product, models) {
    const airsiTaxIds = product.airsi_taxes_id || [];
    if (!airsiTaxIds.length) return [];
    return airsiTaxIds
        .map(id => models['account.tax'].find(t => t.id === id))
        .filter(Boolean);
}

/**
 * Applique ou retire les taxes AIRSI sur une ligne selon l'éligibilité du client.
 * Reproduit exactement la logique de sale.order.line._compute_tax_id côté vente.
 */
function applyAirsiTaxes(line, isPartnerAirsiEligible, models) {
    const product = line.product_id;
    if (!product) return;

    const airsiTaxes = getProductAirsiTaxes(product, models);
    const currentTaxes = line.tax_ids || [];

    if (isPartnerAirsiEligible && airsiTaxes.length) {
        // Ajouter la taxe AIRSI si elle n'est pas déjà présente
        const airsiTax = airsiTaxes[0];
        const alreadyPresent = currentTaxes.some(t => t.id === airsiTax.id);
        if (!alreadyPresent) {
            line.tax_ids = [...currentTaxes, airsiTax];
        }
    } else {
        // Retirer toutes les taxes AIRSI de la ligne
        line.tax_ids = currentTaxes.filter(t => !t.is_airsi);
    }
}

// Patch Order : réagir au changement de client
patch(Order.prototype, {
    set_partner(partner) {
        super.set_partner(partner);
        this._recomputeAirsiTaxes();
    },

    _recomputeAirsiTaxes() {
        const partner = this.get_partner();
        const isEligible = partner ? Boolean(partner.is_airsi_eligible) : false;
        const models = this.models;

        for (const line of this.get_orderlines()) {
            applyAirsiTaxes(line, isEligible, models);
        }
    },
});

// Patch Orderline : appliquer l'AIRSI à la création de la ligne
patch(Orderline.prototype, {
    set_product(product) {
        super.set_product(product);
        const order = this.order;
        if (!order) return;
        const partner = order.get_partner();
        const isEligible = partner ? Boolean(partner.is_airsi_eligible) : false;
        applyAirsiTaxes(this, isEligible, order.models);
    },
});
