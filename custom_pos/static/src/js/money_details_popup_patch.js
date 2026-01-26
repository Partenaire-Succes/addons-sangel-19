/** @odoo-module **/
/**
 * Money Details Popup Customization
 * 
 * Adds a direct amount input field to the money details popup
 * so users can enter an amount directly in addition to counting coins/notes.
 * Also triggers printing of the Prélèvement ticket when confirming.
 * 
 * Features:
 * - Direct amount is CUMULATIVE (adds to stored total, not replace)
 * - Negative values are not allowed
 * - Value persists even after clicking "Ignorer" (cancel)
 */

import { MoneyDetailsPopup } from "@point_of_sale/app/components/popups/money_details_popup/money_details_popup";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

console.log("🔵 money_details_popup_patch.js LOADED");

// Store accumulated total globally so it persists between popup opens (even after cancel)
let _accumulatedTotal = 0;

patch(MoneyDetailsPopup.prototype, {
    /**
     * Override setup to add directAmount state
     */
    setup() {
        super.setup();
        // Direct amount starts at 0 (user types amount to ADD to accumulated total)
        this.state.directAmount = "";
        // Get the action service for printing
        this.actionService = useService("action");
    },

    /**
     * Override computeTotal to include the accumulated total and current input
     */
    computeTotal(moneyDetails = this.state.moneyDetails) {
        // Calculate total from coins/notes
        const coinsNotesTotal = Object.entries(moneyDetails).reduce((total, [value, inputQty]) => {
            const quantity = isNaN(inputQty) ? 0 : inputQty;
            return total + parseFloat(value) * quantity;
        }, 0);
        
        // Add current direct amount input (what user is typing right now)
        const currentDirectAmount = parseFloat(this.state.directAmount) || 0;
        
        // Total = coins/notes + accumulated total + current input
        return coinsNotesTotal + _accumulatedTotal + currentDirectAmount;
    },

    /**
     * Override confirm to include directAmount in total and print prelevement ticket
     */
    async confirm() {
        // Get current input value BEFORE clearing
        const currentDirectAmount = parseFloat(this.state.directAmount) || 0;
        
        // CRITICAL: Clear directAmount FIRST to avoid double-counting in computeTotal
        this.state.directAmount = "";
        
        // THEN add to accumulated total (cumulative behavior)
        if (currentDirectAmount > 0) {
            _accumulatedTotal += currentDirectAmount;
        }

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
        // Add accumulated direct amount to notes
        if (_accumulatedTotal > 0) {
            moneyDetailsNotes += "\t" + _t("Direct: %s\n", this.env.utils.formatCurrency(_accumulatedTotal));
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
            action: this.props.action,
        });

        // Print the prelevement ticket if this is a closing action
        if (this.props.context === "Closing" && this.pos.session && this.pos.session.id) {
            await this.printPrelevementTicket();
        }

        this.props.close();
    },

    /**
     * Print the Prélèvement ticket via report action
     * First saves the counted cash to the database, then prints the report
     */
    async printPrelevementTicket() {
        try {
            const sessionId = this.pos.session.id;
            const countedCash = this.computeTotal();
            
            console.log("🖨️ Printing Prélèvement ticket for session:", sessionId, "Amount:", countedCash);

            // First, save the counted cash amount to the database
            const saveResult = await this.pos.data.call(
                "pos.session",
                "save_cash_count_for_prelevement",
                [sessionId, countedCash]
            );
            console.log("✅ Cash count saved to database. Result:", saveResult);

            // Build the report URL directly for PDF download
            const reportUrl = `/report/pdf/custom_pos.report_prelevement_ticket/${sessionId}`;

            // Fetch the PDF as blob
            const response = await fetch(reportUrl);
            const blob = await response.blob();
            const blobUrl = URL.createObjectURL(blob);
            
            // Open the blob URL in a new window
            const printWindow = window.open(blobUrl, '_blank');
            
            if (printWindow) {
                // Wait for window to load, then trigger print
                printWindow.onload = function() {
                    setTimeout(() => {
                        printWindow.print();
                        // Revoke blob URL after printing
                        setTimeout(() => {
                            URL.revokeObjectURL(blobUrl);
                        }, 5000);
                    }, 500);
                };
                
                // Fallback: if onload doesn't fire (some browsers), trigger print after delay
                setTimeout(() => {
                    if (printWindow && !printWindow.closed) {
                        try {
                            printWindow.print();
                        } catch (e) {
                            console.warn("Print fallback triggered");
                        }
                    }
                }, 2000);
            }

            console.log("✅ Prélèvement ticket print triggered:", reportUrl);
        } catch (error) {
            console.error("❌ Error printing Prélèvement ticket:", error);
        }
    },

    /**
     * Handle direct amount input change
     * - Only positive numbers allowed
     * - Value persists immediately (for persistence even after cancel)
     */
    onDirectAmountInput(ev) {
        // Allow only numbers and decimal point (no minus sign = no negative values)
        let value = ev.target.value.replace(/[^0-9.,]/g, "");
        // Replace comma with dot for decimal
        value = value.replace(",", ".");
        // Ensure it's not negative (already handled by not allowing minus, but double-check)
        const numValue = parseFloat(value) || 0;
        if (numValue < 0) {
            value = "0";
        }
        this.state.directAmount = value;
    },
});

console.log("✅ money_details_popup_patch.js - MoneyDetailsPopup patched");
