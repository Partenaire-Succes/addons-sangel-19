/** @odoo-module */

import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { patch } from "@web/core/utils/patch";

// Patch Orderline component to accept lineNumber prop
patch(Orderline, {
    props: {
        ...Orderline.props,
        lineNumber: { type: Number, optional: true },
    },
});

// Patch Orderline prototype to add negative margin detection
patch(Orderline.prototype, {
    /**
     * Check if the orderline has negative margin (selling below cost)
     * @returns {boolean} true if unit price < standard_price (cost)
     */
    get hasNegativeMargin() {
        const line = this.props.line;
        if (!line || !line.product_id) {
            return false;
        }
        const unitPrice = line.unitDisplayPrice ?? line.price_unit ?? 0;
        const cost = line.product_id.standard_price ?? 0;
        return cost > 0 && unitPrice < cost;
    },
});
