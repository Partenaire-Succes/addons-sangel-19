/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

/**
 * Global Discount (Remise Globale) for POS
 * 
 * Mirrors the logic from custom_sales/models/sale_order_line.py
 * Automatically applies partner discount to eligible product lines.
 * 
 * Conditions for discount:
 * - Product has discount_ligne = true (on product.template)
 * - Partner has discount_eligible = true
 * - Partner has discount_percentage > 0
 * - Current date is within the discount period (if dates are set)
 * 
 * IMPORTANT: Lines with auto-applied global discounts can still merge
 * when adding the same product multiple times.
 */

/**
 * Check if a global discount should be applied based on partner and product settings.
 */
function shouldApplyGlobalDiscount(partner, product) {
    if (!partner || !product) {
        return false;
    }

    // Get the product template (product.product proxies to product_tmpl_id)
    const productTmpl = product.product_tmpl_id || product;

    // Check if product allows line discount
    if (!productTmpl.discount_ligne) {
        return false;
    }

    // Check if partner is eligible for discount
    if (!partner.discount_eligible) {
        return false;
    }

    // Check discount percentage
    const discountPct = partner.discount_percentage || 0;
    if (discountPct <= 0) {
        return false;
    }

    // Check date range
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (partner.discount_start_date) {
        const startDate = new Date(partner.discount_start_date);
        startDate.setHours(0, 0, 0, 0);
        if (startDate > today) {
            return false;
        }
    }

    if (partner.discount_end_date) {
        const endDate = new Date(partner.discount_end_date);
        endDate.setHours(0, 0, 0, 0);
        if (endDate < today) {
            return false;
        }
    }

    return true;
}

/**
 * Get the discount percentage to apply.
 * The discount_percentage field is stored as 0.10 for 10%, so we multiply by 100.
 */
function getGlobalDiscountPercentage(partner) {
    if (!partner || !partner.discount_percentage) {
        return 0;
    }
    return partner.discount_percentage * 100;
}

/**
 * Apply global discount to a single orderline using the proper setDiscount method.
 */
function applyGlobalDiscountToLine(line, partner) {
    if (!line || !line.product_id) {
        return false;
    }

    const product = line.product_id;
    
    if (shouldApplyGlobalDiscount(partner, product)) {
        const discountPercentage = getGlobalDiscountPercentage(partner);
        const currentDiscount = line.getDiscount() || 0;
        
        // Only apply if no manual discount exists, or if global discount is higher
        // Don't override if line has a manually applied discount that's higher
        if (!line._manualDiscountApplied || currentDiscount < discountPercentage) {
            line.setDiscount(discountPercentage);
            line._globalDiscountApplied = true;
            return true;
        }
    } else if (line._globalDiscountApplied) {
        // If conditions no longer met and discount was auto-applied, remove it
        line.setDiscount(0);
        line._globalDiscountApplied = false;
        return true;
    }
    
    return false;
}

/**
 * Apply global discount to all orderlines in an order.
 */
function applyGlobalDiscountToAllLines(order) {
    if (!order || !order.lines) {
        return;
    }

    const partner = order.partner_id;
    
    for (const line of order.lines) {
        if (partner) {
            applyGlobalDiscountToLine(line, partner);
        } else if (line._globalDiscountApplied) {
            // No partner - remove auto-applied discounts
            line.setDiscount(0);
            line._globalDiscountApplied = false;
        }
    }
}

// Patch PosOrderline to allow merging of lines with auto-applied global discounts
patch(PosOrderline.prototype, {
    canBeMergedWith(orderline) {
        // Check if both lines have auto-applied global discounts (or both have no discount)
        // In that case, we can merge them and the discount will be re-applied to the merged line
        const thisHasGlobalDiscount = this._globalDiscountApplied === true;
        const otherHasGlobalDiscount = orderline._globalDiscountApplied === true;
        const thisHasNoDiscount = this.getDiscount() === 0;
        const otherHasNoDiscount = orderline.getDiscount() === 0;
        
        // If both lines qualify for global discount merge (both have global discount or both have no discount)
        // temporarily set discounts to 0 to pass the native merge check
        const canBypassDiscountCheck = (thisHasGlobalDiscount || thisHasNoDiscount) && 
                                        (otherHasGlobalDiscount || otherHasNoDiscount);
        
        if (canBypassDiscountCheck && thisHasGlobalDiscount) {
            // Temporarily set discount to 0 for the merge check
            const originalDiscount = this.discount;
            this.discount = 0;
            
            const canMerge = super.canBeMergedWith(orderline);
            
            // Restore discount
            this.discount = originalDiscount;
            
            return canMerge;
        }
        
        return super.canBeMergedWith(orderline);
    },
});

// Patch PosOrder to apply discount when partner is set
patch(PosOrder.prototype, {
    setPartner(partner) {
        super.setPartner(partner);
        // Apply global discount to all existing orderlines when partner changes
        applyGlobalDiscountToAllLines(this);
    },
});

// Patch PosStore to apply discount AFTER merge logic completes
patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        // Call original method - this creates line and handles merging
        const result = await super.addLineToOrder(vals, order, opts, configure);
        
        // After line creation and merge, apply global discount to the selected line
        // The selected line is either the newly created line or the merged line
        if (order && order.partner_id) {
            const selectedLine = order.getSelectedOrderline();
            if (selectedLine) {
                const discountApplied = applyGlobalDiscountToLine(selectedLine, order.partner_id);
                if (discountApplied) {
                    order.recomputeOrderData();
                }
            }
        }
        
        return result;
    },
});
