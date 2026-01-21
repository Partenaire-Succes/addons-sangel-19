/** @odoo-module **/
/**
 * Money Details Popup Customization
 * 
 * Adds a direct amount input field to the money details popup
 * so users can enter an amount directly in addition to counting coins/notes
 */

import { MoneyDetailsPopup } from "@point_of_sale/app/components/popups/money_details_popup/money_details_popup";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

console.log("🔵 money_details_popup_patch.js LOADED");

patch(MoneyDetailsPopup.prototype, {
    /**
     * Override setup to add directAmount state
     * Load from props if available (for persistence between popup opens)
     */
    setup() {
        super.setup();
        // Add direct amount input to state - load from props if previously saved
        this.state.directAmount = this.props.directAmount || "";
    },

    /**
     * Override computeTotal to include the direct amount input
     */
    computeTotal(moneyDetails = this.state.moneyDetails) {
        // Calculate total from coins/notes
        const coinsNotesTotal = Object.entries(moneyDetails).reduce((total, [value, inputQty]) => {
            const quantity = isNaN(inputQty) ? 0 : inputQty;
            return total + parseFloat(value) * quantity;
        }, 0);
        
        // Add direct amount if valid
        const directAmount = parseFloat(this.state.directAmount) || 0;
        
        return coinsNotesTotal + directAmount;
    },

    /**
     * Override confirm to include directAmount in payload
     */
    confirm() {
        let moneyDetailsNotes = !this.pos.currency.isZero(this.computeTotal())
            ? this.props.context + " details: \n"
            : null;
        this.pos.models["pos.bill"].forEach((bill) => {
            if (this.state.moneyDetails[bill.value]) {
                moneyDetailsNotes +=
                    "\t" +
                    `${this.state.moneyDetails[bill.value]} x ${this.env.utils.formatCurrency(
                        bill.value
                    )}\n`;
            }
        });
        // Add direct amount to notes if entered
        const directAmount = parseFloat(this.state.directAmount) || 0;
        if (directAmount > 0) {
            moneyDetailsNotes += "\t" + _t("Direct: %s\n", this.env.utils.formatCurrency(directAmount));
        }
        if (moneyDetailsNotes) {
            moneyDetailsNotes += _t(
                "Total: %s",
                this.env.utils.formatCurrency(this.computeTotal())
            );
        }
        this.props.getPayload({
            total: this.computeTotal(),
            moneyDetailsNotes,
            moneyDetails: { ...this.state.moneyDetails },
            directAmount: this.state.directAmount, // Include directAmount in payload
            action: this.props.action,
        });
        this.props.close();
    },

    /**
     * Handle direct amount input change
     */
    onDirectAmountInput(ev) {
        // Allow only numbers and decimal point
        let value = ev.target.value.replace(/[^0-9.,]/g, "");
        // Replace comma with dot for decimal
        value = value.replace(",", ".");
        this.state.directAmount = value;
    },
});

console.log("✅ money_details_popup_patch.js - MoneyDetailsPopup patched");
