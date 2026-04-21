/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

function getProductAirsiTaxes(product, models) {
    const airsiTaxIds = product.airsi_taxes_id || [];
    if (!airsiTaxIds.length) return [];
    return airsiTaxIds
        .map(id => models['account.tax'].find(t => t.id === id))
        .filter(Boolean);
}

function applyAirsiTaxes(line, isPartnerAirsiEligible, models) {
    const product = line.product_id;
    if (!product) return;

    const airsiTaxes = getProductAirsiTaxes(product, models);
    const currentTaxes = line.tax_ids || [];

    if (isPartnerAirsiEligible && airsiTaxes.length) {
        const airsiTax = airsiTaxes[0];
        const alreadyPresent = currentTaxes.some(t => t.id === airsiTax.id);
        if (!alreadyPresent) {
            line.tax_ids = [...currentTaxes, airsiTax];
        }
    } else {
        line.tax_ids = currentTaxes.filter(t => !t.is_airsi);
    }
}

patch(PosOrder.prototype, {
    setPartner(partner) {
        super.setPartner(partner);
        this._recomputeAirsiTaxes();
    },

    _recomputeAirsiTaxes() {
        const partner = this.getPartner();
        const isEligible = partner ? Boolean(partner.is_airsi_eligible) : false;
        const models = this.models;
        for (const line of (this.lines || [])) {
            applyAirsiTaxes(line, isEligible, models);
        }
    },
});

patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        const order = this.order_id;
        if (!order) return;
        const partner = order.getPartner();
        const isEligible = partner ? Boolean(partner.is_airsi_eligible) : false;
        applyAirsiTaxes(this, isEligible, this.models);
    },
});
