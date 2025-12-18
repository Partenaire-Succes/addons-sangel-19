/** @odoo-module **/

console.warn("🔴 payment_screen_patch.js LOADED - Module is being imported");

import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

console.warn("🟢 payment_screen_patch.js - All imports successful, applying patch now");

patch(ActionpadWidget.prototype, {
    
    /**
     * Parse and return preset remise percentages from config
     * @returns {Array} List of preset remise percentages
     */
    getPresetRemiseList() {
        console.log("🔍 Retrieving preset remise percentages");
        
        // console.log("Config object:", this.pos.config);
        const presetString = this.pos?.config?.preset_remise_percentages || "10,25,50";
        console.log("Raw presetString value:", presetString);
        console.log("Type of presetString:", typeof presetString);
        
        if (!presetString) {
            console.warn("⚠️ No preset_remise_percentages configured - returning empty array");
            return [];
        }
        
        try {
            // Split by comma and convert to integers, filter out invalid values
            const values = presetString
                .split(',')
                .map(v => parseInt(v.trim()))
                .filter(v => !isNaN(v) && v >= 0 && v <= 100);
            
            console.log("Parsed values:", values);
            
            // Remove duplicates and sort
            const result = [...new Set(values)].sort((a, b) => a - b);
            console.log("✅ Final result:", result);
            return result;
        } catch (e) {
            console.warn("❌ Error parsing preset_remise_percentages:", e);
            return [];
        }
    },

    /**
     * Apply preset remise percentage to the current order line
     * @param {Number} percentage - The remise percentage to apply
     */
    async applyPresetRemise(percentage) {
        const currentOrder = this.pos.getOrder();
        if (!currentOrder) {
            this.dialog.add(AlertDialog, {
                title: _t("No Order"),
                body: _t("There is no active order to apply remise to."),
            });
            return;
        }

        // Get the selected order line or the last line
        const orderLines = currentOrder.getOrderlines();
        if (!orderLines || orderLines.length === 0) {
            this.dialog.add(AlertDialog, {
                title: _t("No Products"),
                body: _t("Please add a product to the order before applying a remise."),
            });
            return;
        }

        // Try to get the selected line, otherwise use the last line added
        let selectedLine = currentOrder.getSelectedOrderline && currentOrder.getSelectedOrderline();
        if (!selectedLine && typeof currentOrder.getLastOrderline === 'function') {
            selectedLine = currentOrder.getLastOrderline();
        } else if (!selectedLine && orderLines.length > 0) {
            selectedLine = orderLines[orderLines.length - 1];
        }

        if (!selectedLine) {
            this.dialog.add(AlertDialog, {
                title: _t("No Product Selected"),
                body: _t("Please select a product line to apply the remise."),
            });
            return;
        }

        // Check if line already has a discount (use getter if available)
        try {
            const existingDiscount =
                typeof selectedLine.getDiscount === 'function' ? selectedLine.getDiscount() : selectedLine.discount || 0;
            if (existingDiscount > 0) {
                console.warn(`Line already has ${existingDiscount}% discount. Overriding with ${percentage}%`);
            }

            // Apply the remise using the correct API
            if (typeof selectedLine.setDiscount === 'function') {
                selectedLine.setDiscount(percentage);
            } else if (typeof selectedLine.set_discount === 'function') {
                // fallback for older API names
                selectedLine.set_discount(percentage);
            } else {
                throw new Error('No setDiscount method available on orderline');
            }

            // Optional: Show confirmation feedback
            console.log(`Applied ${percentage}% remise to product: ${selectedLine.product_id?.display_name || selectedLine.getProduct?.()?.display_name || 'unknown'}`);
        } catch (e) {
            console.error("Error applying remise:", e);
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("Failed to apply the remise. Please try again."),
            });
        }
    },
});

// VERIFICATION: Check if patch was applied successfully
console.warn("🟡 payment_screen_patch.js - Verifying patch applied (500ms delay)");
setTimeout(() => {
    try {
        console.warn("⏱️ [PATCH VERIFICATION] Checking if ActionpadWidget prototype has been patched");
        if (ActionpadWidget.prototype.getPresetRemiseList) {
            console.warn("✅ [PATCH VERIFICATION] getPresetRemiseList method EXISTS on ActionpadWidget.prototype");
            console.warn("✅ [PATCH VERIFICATION] Method is ready - will be called when ActionpadWidget renders");
        } else {
            console.warn("❌ [PATCH VERIFICATION] getPresetRemiseList method NOT FOUND on ActionpadWidget.prototype");
        }
        if (ActionpadWidget.prototype.applyPresetRemise) {
            console.warn("✅ [PATCH VERIFICATION] applyPresetRemise method EXISTS on ActionpadWidget.prototype");
        } else {
            console.warn("❌ [PATCH VERIFICATION] applyPresetRemise method NOT FOUND on ActionpadWidget.prototype");
        }
    } catch (e) {
        console.error("❌ [PATCH VERIFICATION] Error checking patch:", e);
    }
}, 500);
