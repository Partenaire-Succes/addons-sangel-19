/** @odoo-module **/

import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { PosOrder } from "@point_of_sale/app/models/pos_order"; // ✅ Odoo 19 Model Path
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PaymentScreenStatus } from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import { PosStore } from "@point_of_sale/app/services/pos_store"; // ✅ Import the Main Store
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

console.log("🔴 Loading Custom POS Patch for Odoo 19...");

patch(PosStore.prototype, {

    async openLoyaltyWizard() {
        const order = this.getOrder();
        if (!order) return;

        const partner = order.getPartner();
        if (!partner) {
            this.dialog.add(AlertDialog, {
                title: _t("Aucun client"),
                body: _t("Veuillez d'abord sélectionner un client."),
            });
            return;
        }

        // Check if partner has a loyalty card
        const loyaltyCards = await this.env.services.orm.searchRead(
            "loyalty.card",
            [["partner_id", "=", partner.id]],
            ["id", "points"],
            { limit: 1 }
        );

        if (!loyaltyCards || loyaltyCards.length === 0) {
            this.dialog.add(AlertDialog, {
                title: _t("Pas de carte de fidélité"),
                body: _t("Ce client n'a pas de carte de fidélité. Veuillez en créer une d'abord."),
            });
            return;
        }

        const currentPoints = loyaltyCards[0].points || 0;

        // Use NumberPopup to get the rendu monnaie amount
        const result = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Rendu monnaie (FCFA)"),
            subtitle: _t(`Client: ${partner.name} | Solde actuel: ${currentPoints.toFixed(2)} pts`),
            startingValue: "0",
        });

        if (result && parseFloat(result) > 0) {
            const amount = parseFloat(result);
            order.set_rendu_monnaie(amount);
            console.log("✅ Rendu monnaie set on order:", amount, "(Points will be updated on payment validation)");
        } else {
            console.log("ℹ️ Rendu monnaie cancelled or invalid amount");
        }
    },
});

patch(PosOrder.prototype, {
    setup() {
        super.setup(...arguments);
        this.rendu_monnaie = this.rendu_monnaie || 0;
    },
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.rendu_monnaie = this.rendu_monnaie;
        return json;
    },
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.rendu_monnaie = json.rendu_monnaie || 0;
    },
    set_rendu_monnaie(amount) {
        this.rendu_monnaie = amount;
    },
    get_rendu_monnaie() {
        return this.rendu_monnaie || 0;
    }
});


patch(PaymentScreen.prototype, {
    get paymentScreenStatusProps() {
        // Standard Odoo way to pass props to the status component
        const props = super.paymentScreenStatusProps;
        const order = this.pos.getOrder();
        return {
            ...props,
            renduMonnaie: order ? order.get_rendu_monnaie() : 0,
        };
    }
});

patch(PaymentScreenStatus.prototype, {

    // Override Change (Monnaie) Calculation
    get changeText() {
        const order = this.props.order;
        const change = order.getChange(); // Original Change
        const rendu = order.get_rendu_monnaie ? order.get_rendu_monnaie() : 0;

        // Subtract Rendu from Change
        return this.env.utils.formatCurrency(change - rendu);
    },

    // Override Remaining (Restant) Calculation
    get remainingText() {
        const order = this.props.order;
        const rendu = order.get_rendu_monnaie ? order.get_rendu_monnaie() : 0;

        // If order has zero remaining (fully paid), we still subtract rendu
        // (This might result in a negative number, effectively "change")
        if (order.orderHasZeroRemaining) {
            return this.env.utils.formatCurrency(0 - rendu);
        }

        // Standard calculation based on taxTotals
        if (order.taxTotals) {
            const { order_remaining, order_sign } = order.taxTotals;
            const remaining = order_sign * order_remaining;

            // Subtract Rendu from Remaining
            return this.env.utils.formatCurrency(remaining - rendu);
        }

        // Fallback
        return this.env.utils.formatCurrency(0 - rendu);
    }
});
// Note: We patch the CLASS to add static props, not the prototype.
patch(PaymentScreenStatus, {
    props: {
        ...PaymentScreenStatus.props,
        renduMonnaie: { type: Number, optional: true },
    },
});
