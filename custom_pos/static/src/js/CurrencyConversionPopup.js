/** @odoo-module **/
/**
 * Currency Conversion Popup for POS Payment Screen
 * 
 * Allows users to enter an amount in a foreign currency and see the
 * converted amount in the company currency (USD). On confirm, the
 * converted amount is added to the selected Cash payment line.
 */

import { Component, onWillStart, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class CurrencyConversionPopup extends Component {
    static template = "custom_pos.CurrencyConversionPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
    };

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            currencies: [],
            selectedCurrencyId: null,
            foreignAmount: "",
            convertedAmount: 0,
            isLoading: true,
            isConverting: false,
            error: null,
            companyCurrency: null,
            selectedCurrency: null,
        });

        onWillStart(async () => {
            await this.loadCurrencies();
        });
    }

    /**
     * Load active currencies from the server
     */
    async loadCurrencies() {
        try {
            this.state.isLoading = true;
            this.state.error = null;

            const result = await this.orm.call(
                "res.currency",
                "search_read",
                [],
                {
                    domain: [["active", "=", true], ["id", "!=", this.pos.currency.id]],
                    fields: ["id", "name", "symbol", "rate", "position", "decimal_places", "rounding"],
                    order: "name",
                }
            );

            // Calculate conversion rates (1 foreign = X company currency)
            const companyCurrency = this.pos.currency;
            this.state.companyCurrency = companyCurrency;

            this.state.currencies = result.map(curr => ({
                ...curr,
                // rate in Odoo is relative to EUR base, we need rate to company currency
                // For simplicity, we'll compute on conversion
                displayName: `${curr.name} (${curr.symbol})`,
            }));

            // Pre-select first currency if available
            if (this.state.currencies.length > 0) {
                this.state.selectedCurrencyId = this.state.currencies[0].id;
                this.state.selectedCurrency = this.state.currencies[0];
            }

        } catch (error) {
            console.error("Error loading currencies:", error);
            this.state.error = _t("Failed to load currencies. Please try again.");
        } finally {
            this.state.isLoading = false;
        }
    }

    /**
     * Handle currency selection change
     */
    onCurrencyChange(ev) {
        const currencyId = parseInt(ev.target.value);
        this.state.selectedCurrencyId = currencyId;
        this.state.selectedCurrency = this.state.currencies.find(c => c.id === currencyId);

        // Re-convert if amount exists
        if (this.state.foreignAmount) {
            this.convertAmount();
        }
    }

    /**
     * Handle amount input change
     */
    onAmountInput(ev) {
        // Allow only numbers and decimal point
        let value = ev.target.value.replace(/[^0-9.,]/g, "");
        // Replace comma with dot for decimal
        value = value.replace(",", ".");
        this.state.foreignAmount = value;

        // Debounce conversion
        clearTimeout(this._convertTimeout);
        this._convertTimeout = setTimeout(() => {
            this.convertAmount();
        }, 300);
    }

    /**
     * Convert the foreign amount to company currency
     */
    async convertAmount() {
        const amount = parseFloat(this.state.foreignAmount);
        if (!amount || !this.state.selectedCurrencyId) {
            this.state.convertedAmount = 0;
            return;
        }

        try {
            this.state.isConverting = true;

            // Call the conversion endpoint
            const result = await this.env.services.rpc("/pos/convert_currency", {
                currency_id: this.state.selectedCurrencyId,
                amount: amount,
            });

            if (result.status === "success") {
                this.state.convertedAmount = result.converted_amount;
                this.state.error = null;
            } else {
                this.state.error = result.message || _t("Conversion failed");
                this.state.convertedAmount = 0;
            }

        } catch (error) {
            console.error("Error converting currency:", error);
            // Fallback: use local rate calculation
            const currency = this.state.selectedCurrency;
            if (currency && currency.rate) {
                // Odoo rate is inverse (company currency / foreign currency)
                // We need: amount in foreign * rate = amount in company
                this.state.convertedAmount = amount / currency.rate;
            } else {
                this.state.error = _t("Conversion failed. Please check rates.");
            }
        } finally {
            this.state.isConverting = false;
        }
    }

    /**
     * Format amount with currency symbol
     */
    formatCurrency(amount, currency) {
        if (!currency) return amount.toFixed(2);

        const formatted = amount.toFixed(currency.decimal_places || 2);
        if (currency.position === "before") {
            return `${currency.symbol} ${formatted}`;
        } else {
            return `${formatted} ${currency.symbol}`;
        }
    }

    /**
     * Get formatted converted amount display
     */
    get formattedConvertedAmount() {
        return this.formatCurrency(this.state.convertedAmount, this.state.companyCurrency);
    }

    /**
     * Check if rate info section should be displayed
     */
    get showRateInfo() {
        const foreignAmount = parseFloat(this.state.foreignAmount) || 0;
        return (
            this.state.selectedCurrency &&
            foreignAmount > 0 &&
            this.state.convertedAmount > 0
        );
    }

    /**
     * Get formatted exchange rate for display
     */
    get formattedExchangeRate() {
        const foreignAmount = parseFloat(this.state.foreignAmount) || 0;
        if (foreignAmount === 0) return "0.0000";
        return (this.state.convertedAmount / foreignAmount).toFixed(4);
    }

    /**
     * Check if confirm button should be enabled
     */
    get canConfirm() {
        return (
            this.state.selectedCurrencyId &&
            parseFloat(this.state.foreignAmount) > 0 &&
            this.state.convertedAmount > 0 &&
            !this.state.isConverting
        );
    }

    /**
     * Confirm and return the converted amount
     */
    confirm() {
        if (!this.canConfirm) return;

        const payload = {
            convertedAmount: this.state.convertedAmount,
            foreignAmount: parseFloat(this.state.foreignAmount),
            currency: this.state.selectedCurrency,
            companyCurrency: this.state.companyCurrency,
        };

        if (this.props.getPayload) {
            this.props.getPayload(payload);
        }

        this.props.close();
    }

    /**
     * Cancel and close the popup
     */
    cancel() {
        this.props.close();
    }
}
