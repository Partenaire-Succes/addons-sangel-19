/** @odoo-module **/
/**
 * Payment Screen Currency Conversion Patch
 * 
 * Adds a currency conversion button to the POS payment screen,
 * visible only when the "Espèces" (Cash) payment method is selected.
 * The button opens a popup allowing the user to enter an amount in
 * a foreign currency and have it converted to the company currency.
 */

import { CurrencyConversionPopup } from "@custom_pos/js/CurrencyConversionPopup";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

console.log("🔵 currency_payment_screen_patch.js LOADED");

patch(PaymentScreen.prototype, {
    /**
     * Check if the currently selected payment line is a Cash payment method
     * @returns {boolean}
     */
    isCashPaymentSelected() {
        const selectedLine = this.selectedPaymentLine;
        if (!selectedLine) return false;

        // Check if payment method is cash type
        const paymentMethod = selectedLine.payment_method_id;
        return paymentMethod && paymentMethod.type === "cash";
    },

    /**
     * Check if currency conversion button should be visible
     * Only visible when:
     * - A payment line is selected
     * - The selected payment line is "cash" type (Espèces)
     * @returns {boolean}
     */
    get showCurrencyConversionButton() {
        return this.isCashPaymentSelected();
    },

    /**
     * Open the currency conversion popup
     */
    async openCurrencyConversionPopup() {
        if (!this.isCashPaymentSelected()) {
            this.notification.add(
                _t("Veuillez sélectionner un mode de paiement en espèces."),
                { type: "warning" }
            );
            return;
        }

        // Open the currency conversion popup using POS makeAwaitable helper
        const payload = await makeAwaitable(this.dialog, CurrencyConversionPopup, {});

        // If user confirmed and we have a converted amount
        if (payload && payload.convertedAmount > 0) {
            await this.addConvertedAmountToPayment(payload);
        }
    },

    /**
     * Set the converted amount as the cash payment line amount
     * @param {Object} payload - The conversion result
     * @param {number} payload.convertedAmount - Amount in company currency
     * @param {number} payload.foreignAmount - Original amount in foreign currency
     * @param {Object} payload.currency - The source currency object
     */
    async addConvertedAmountToPayment(payload) {
        const { convertedAmount, foreignAmount, currency } = payload;
        const selectedLine = this.selectedPaymentLine;

        if (!selectedLine) {
            // No payment line selected, create a new cash payment line
            const cashMethod = this.payment_methods_from_config.find(m => m.type === "cash");
            if (cashMethod) {
                this.addNewPaymentLine(cashMethod);
            }
        }

        // Get the (possibly new) selected line
        const paymentLine = this.selectedPaymentLine || this.paymentLines.at(-1);

        if (paymentLine) {
            // Set the payment line amount directly to the converted amount (replaces existing)
            paymentLine.setAmount(convertedAmount);

            // Update the number buffer to reflect the new amount
            this.numberBuffer.set(convertedAmount.toString());

            // Show confirmation notification
            const currencySymbol = currency?.symbol || "";
            const companyCurrencySymbol = this.pos.currency?.symbol || "$";

            this.notification.add(
                _t("%(foreign)s %(foreignSymbol)s converti en %(converted)s %(companySymbol)s.", {
                    foreign: foreignAmount.toFixed(2),
                    foreignSymbol: currencySymbol,
                    converted: convertedAmount.toFixed(2),
                    companySymbol: companyCurrencySymbol,
                }),
                { type: "success", sticky: false }
            );

            console.log(`💱 Currency conversion: ${foreignAmount} ${currency?.name || "?"} → ${convertedAmount} ${this.pos.currency?.name || "USD"}`);
        }
    },
});

console.log("✅ currency_payment_screen_patch.js - PaymentScreen patched with currency conversion");
