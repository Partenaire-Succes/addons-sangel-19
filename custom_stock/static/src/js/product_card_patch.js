/** @odoo-module */

import { ProductCatalogKanbanRecord } from "@product/product_catalog/kanban_record";
import { patch } from "@web/core/utils/patch";

/**
 * Extend ProductCatalogKanbanRecord to expose max quantity and pending reception data.
 * Data is fetched from record fields, NOT from productCatalogData (to avoid prop validation errors).
 */
patch(ProductCatalogKanbanRecord.prototype, {
    /**
     * Get the maximum quantity from orderpoint rules.
     * @returns {number}
     */
    get maxQtyOrderpoint() {
        return this.props.record.data.max_qty_orderpoint || 0;
    },

    /**
     * Get the pending reception quantity (draft/ready receptions).
     * @returns {number}
     */
    get pendingReceptionQty() {
        return this.props.record.data.pending_reception_qty || 0;
    },

    /**
     * Check if max quantity should be displayed.
     * @returns {boolean}
     */
    get showMaxQty() {
        return this.maxQtyOrderpoint > 0;
    },

    /**
     * Check if pending reception should be displayed.
     * @returns {boolean}
     */
    get showPendingReception() {
        return this.pendingReceptionQty > 0;
    },
});
