/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Retourne les taxes AIRSI d'un produit.
 * Gère les deux formats possibles : tableau d'objets ou tableau d'IDs.
 */
function getAirsiTaxes(product, models) {
    const raw = product.airsi_taxes_id;
    if (!raw || !raw.length) return [];

    if (typeof raw[0] === 'object' && raw[0] !== null) {
        return raw.filter(t => t && t.is_airsi);
    }

    return raw
        .map(id => models['account.tax'].find(t => t.id === id))
        .filter(t => t && t.is_airsi);
}

function applyAirsiOnLine(line, isEligible, models) {
    const product = line.product_id;
    if (!product) return;

    const airsiTaxes = getAirsiTaxes(product, models);
    const currentTaxes = line.tax_ids || [];

    if (isEligible && airsiTaxes.length) {
        const airsiTax = airsiTaxes[0];
        if (!currentTaxes.some(t => t.id === airsiTax.id)) {
            line.tax_ids = [...currentTaxes, airsiTax];
        }
    } else {
        const filtered = currentTaxes.filter(t => !t.is_airsi);
        if (filtered.length !== currentTaxes.length) {
            line.tax_ids = filtered;
        }
    }
}

// ─── Patch 1 : ajout d'un produit ────────────────────────────────────────────
// Applique l'AIRSI sur la nouvelle ligne juste après sa création.

patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        const line = await super.addLineToOrder(vals, order, opts, configure);
        if (!line) return line;

        const partner = order.getPartner();
        const isEligible = partner ? Boolean(partner.is_airsi_eligible) : false;
        applyAirsiOnLine(line, isEligible, this.models);

        return line;
    },
});

// ─── Patch 2 : changement de client ──────────────────────────────────────────
// Recalcule l'AIRSI sur toutes les lignes quand le client change.

patch(PosOrder.prototype, {
    setPartner(partner) {
        super.setPartner(partner);
        const isEligible = partner ? Boolean(partner.is_airsi_eligible) : false;
        for (const line of (this.lines || [])) {
            applyAirsiOnLine(line, isEligible, this.models);
        }
    },
});
