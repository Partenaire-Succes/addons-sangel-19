/** @odoo-module **/
/**
 * Closing Popup Customization
 * 
 * Removes payment summary section from the closing popup
 * and makes cash count input read-only (updated only from MoneyDetailsPopup)
 * Custom "Écart de règlement" dialog with colored messages based on difference
 * Prints "Clôture de caisse" report on session close
 */

import { markup } from "@odoo/owl";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { MoneyDetailsPopup } from "@point_of_sale/app/components/popups/money_details_popup/money_details_popup";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

console.log("🔵 closing_popup_patch.js LOADED");

// Store the last confirmed cash count globally so it persists after clicking Ignorer
let _lastConfirmedCashCount = 0;

patch(ClosePosPopup.prototype, {
    /**
     * Override setup to restore persisted cash count
     */
    setup() {
        super.setup();
        // Restore the last confirmed cash count if any
        if (_lastConfirmedCashCount > 0 && this.props.default_cash_details) {
            // Use setTimeout to ensure state is initialized
            setTimeout(() => {
                if (this.state.payments && this.state.payments[this.props.default_cash_details.id]) {
                    this.state.payments[this.props.default_cash_details.id].counted = 
                        this.env.utils.formatCurrency(_lastConfirmedCashCount, false);
                }
            }, 0);
        }
    },
    /**
     * Override to prevent manual cash input editing
     * Cash count should only be updated from MoneyDetailsPopup
     */
    setManualCashInput(amount) {
        // Do nothing - we want cash count to be read-only
        // and only updated from the MoneyDetailsPopup
    },

    /**
     * Override openDetailsPopup to handle direct amount
     */
    async openDetailsPopup() {
        const action = _t("Cash control - closing");
        this.hardwareProxy.openCashbox(action);
        this.dialog.add(MoneyDetailsPopup, {
            moneyDetails: this.moneyDetails,
            action: action,
            getPayload: (payload) => {
                const { total, moneyDetailsNotes, moneyDetails } = payload;
                this.state.payments[this.props.default_cash_details.id].counted =
                    this.env.utils.formatCurrency(total, false);
                // Store globally for persistence after Ignorer
                _lastConfirmedCashCount = total;
                if (moneyDetailsNotes) {
                    this.state.notes = moneyDetailsNotes;
                }
                this.moneyDetails = moneyDetails;
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

    /**
     * Override closeSession to print the cloture de caisse report after successful close
     */
    async closeSession() {
        // Store session ID before closing (as session will be set to closed)
        const sessionId = this.pos.session.id;
        
        // Call the original closeSession logic
        this.pos._resetConnectedCashier();
        
        // If there are orders in the db left unsynced, we try to sync.
        const syncSuccess = await this.pos.pushOrdersWithClosingPopup();
        if (!syncSuccess) {
            return;
        }
        
        if (this.pos.config.cash_control) {
            // Remove formatting (spaces, commas, etc.) from the counted cash string before parsing
            // formatCurrency returns strings like "200 000" or "200,000" which parseFloat can't handle
            const countedCashString = this.state.payments[this.props.default_cash_details.id].counted;
            const cleanedCashString = countedCashString.toString().replace(/[\s,\u00a0]/g, '');
            const countedCash = parseFloat(cleanedCashString) || 0;
            
            const response = await this.pos.data.call(
                "pos.session",
                "post_closing_cash_details",
                [this.pos.session.id],
                {
                    counted_cash: countedCash,
                }
            );

            if (!response.successful) {
                return this.handleClosingError(response);
            }
        }

        try {
            await this.pos.data.call("pos.session", "update_closing_control_state_session", [
                this.pos.session.id,
                this.state.notes,
            ]);
        } catch (error) {
            if (!error.data && error.data.message !== "This session is already closed.") {
                throw error;
            }
        }

        try {
            const bankPaymentMethodDiffPairs = this.props.non_cash_payment_methods
                .filter((pm) => pm.type == "bank")
                .map((pm) => [pm.id, this.getDifference(pm.id)]);
            const response = await this.pos.data.call(
                "pos.session",
                "close_session_from_ui",
                [this.pos.session.id, bankPaymentMethodDiffPairs],
                {
                    context: {
                        device_identifier: this.pos.device.identifier,
                    },
                }
            );
            if (!response.successful) {
                return this.handleClosingError(response);
            }
            this.pos.session.state = "closed";
            
            // Print the Clôture de Caisse report
            await this.printClotureCaisseReport(sessionId);
            
            this.pos.router.close();
        } catch (error) {
            // Handle connection lost error
            if (error.name === "ConnectionLostError") {
                throw error;
            } else {
                await this.handleClosingControlError();
            }
        } finally {
            localStorage.removeItem(`pos.session.${odoo.pos_config_id}`);
        }
    },

    /**
     * Print the Clôture de Caisse report for the closed session
     */
    async printClotureCaisseReport(sessionId) {
        try {
            console.log("🖨️ Printing Clôture de Caisse report for session:", sessionId);
            
            // Build the PDF report URL
            const reportUrl = `/report/pdf/custom_pos.report_cloture_caisse_ticket/${sessionId}`;
            
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
            
            console.log("✅ Clôture de Caisse report print triggered");
        } catch (error) {
            console.error("❌ Error printing Clôture de Caisse report:", error);
            // Don't block closing if report fails - just log the error
        }
    },
});

console.log("✅ closing_popup_patch.js - ClosePosPopup patched");
