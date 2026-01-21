/** @odoo-module **/
/**
 * Closing Popup Customization
 * 
 * Removes payment summary section from the closing popup
 * and makes cash count input read-only (updated only from MoneyDetailsPopup)
 * Custom "Écart de règlement" dialog with colored messages based on difference
 */

import { markup } from "@odoo/owl";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { MoneyDetailsPopup } from "@point_of_sale/app/components/popups/money_details_popup/money_details_popup";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

console.log("🔵 closing_popup_patch.js LOADED");

patch(ClosePosPopup.prototype, {
    /**
     * Override to prevent manual cash input editing
     * Cash count should only be updated from MoneyDetailsPopup
     */
    setManualCashInput(amount) {
        // Do nothing - we want cash count to be read-only
        // and only updated from the MoneyDetailsPopup
    },

    /**
     * Override openDetailsPopup to pass and store directAmount
     */
    async openDetailsPopup() {
        const action = _t("Cash control - closing");
        this.hardwareProxy.openCashbox(action);
        this.dialog.add(MoneyDetailsPopup, {
            moneyDetails: this.moneyDetails,
            directAmount: this.directAmount || "", // Pass stored directAmount
            action: action,
            getPayload: (payload) => {
                const { total, moneyDetailsNotes, moneyDetails, directAmount } = payload;
                this.state.payments[this.props.default_cash_details.id].counted =
                    this.env.utils.formatCurrency(total, false);
                if (moneyDetailsNotes) {
                    this.state.notes = moneyDetailsNotes;
                }
                this.moneyDetails = moneyDetails;
                this.directAmount = directAmount; // Store directAmount for next popup open
            },
            context: "Closing",
        });
    },

    /**
     * Override confirm to show colored message based on écart sign
     * Green for positive (surplus), red for negative (shortage)
     */
    async confirm() {
        if (!this.pos.config.cash_control || this.pos.currency.isZero(this.getMaxDifference())) {
            await this.closeSession();
            return;
        }
        
        // Get the cash difference
        const cashDiff = this.getDifference(this.props.default_cash_details.id);
        const formattedAmount = this.env.utils.formatCurrency(Math.abs(cashDiff));
        
        // Build colored message based on difference sign
        let messageBody;
        if (cashDiff > 0) {
            // Positive = surplus (excédent)
            messageBody = markup(`
                <p style="color: #28a745; font-weight: bold; font-size: 1.1em;">
                    Excédent de caisse : +${formattedAmount}
                </p>
                <p>Voulez-vous enregistrer cette différence dans la comptabilité ?</p>
            `);
        } else {
            // Negative = shortage (manquant)
            messageBody = markup(`
                <p style="color: #dc3545; font-weight: bold; font-size: 1.1em;">
                    Manquant de caisse : -${formattedAmount}
                </p>
                <p>Voulez-vous enregistrer cette différence dans la comptabilité ?</p>
            `);
        }
        
        if (this.hasUserAuthority()) {
            const response = await ask(this.dialog, {
                title: _t("Écart de règlement"),
                body: messageBody,
                confirmLabel: _t("Poursuivre"),
                cancelLabel: _t("Ignorer"),
            });
            if (response) {
                return this.closeSession();
            }
            return;
        }
        
        // User doesn't have authority - show manager needed message
        this.dialog.add(ConfirmationDialog, {
            title: _t("Écart de règlement"),
            body: _t(
                "La différence maximale autorisée est de %s.\nVeuillez contacter votre responsable pour accepter l'écart de fermeture.",
                this.env.utils.formatCurrency(this.props.amount_authorized_diff)
            ),
        });
    },
});

console.log("✅ closing_popup_patch.js - ClosePosPopup patched");
