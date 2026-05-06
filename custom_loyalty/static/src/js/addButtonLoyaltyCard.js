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

        let currentPoints = 0;
        let hasLoyaltyCard = false;

        // Essayer de récupérer la carte de fidélité via RPC (mode en ligne)
        try {
            const loyaltyCards = await this.env.services.orm.searchRead(
                "loyalty.card",
                [["partner_id", "=", partner.id]],
                ["id", "points"],
                { limit: 1 }
            );

            if (loyaltyCards && loyaltyCards.length > 0) {
                hasLoyaltyCard = true;
                currentPoints = loyaltyCards[0].points || 0;
            }
        } catch (error) {
            // Mode hors-ligne - utiliser les données locales
            console.warn("Mode hors-ligne détecté - recherche carte fidélité locale:", error.message || error);
            
            // Chercher dans les données de fidélité locales (couponPointChanges de la commande)
            // ou dans les cartes déjà chargées pour ce partenaire
            const loyaltyCardsLocal = this.models["loyalty.card"];
            if (loyaltyCardsLocal) {
                // Parcourir toutes les cartes en cache pour trouver celle du partenaire
                for (const card of loyaltyCardsLocal.getAll()) {
                    const cardPartnerId = card.partner_id?.id || card.partner_id;
                    if (cardPartnerId === partner.id) {
                        hasLoyaltyCard = true;
                        currentPoints = card.points || 0;
                        console.log("✅ Carte fidélité trouvée localement:", card);
                        break;
                    }
                }
            }
            
            // Si toujours pas trouvé, vérifier si le partenaire a le flag is_loyalty
            if (!hasLoyaltyCard && partner.is_loyalty) {
                // Le partenaire a une carte mais elle n'est pas en cache
                // Permettre quand même la fonctionnalité en mode dégradé
                hasLoyaltyCard = true;
                currentPoints = 0; // Points inconnus hors-ligne
                console.warn("Mode hors-ligne: Carte fidélité supposée (is_loyalty=true), points inconnus");
            }
        }

        if (!hasLoyaltyCard) {
            this.dialog.add(AlertDialog, {
                title: _t("Pas de carte de fidélité"),
                body: _t("Ce client n'a pas de carte de fidélité. Veuillez en créer une d'abord."),
            });
            return;
        }

        // Afficher le solde comme "inconnu" si en mode hors-ligne et pas de données
        const pointsDisplay = currentPoints > 0 ? currentPoints.toFixed(2) : "?";

        // Use NumberPopup to get the rendu monnaie amount
        // Show current rendu_monnaie as starting value so user can see/reset it
        const currentRendu = order.get_rendu_monnaie() || 0;
        const result = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Rendu monnaie (FCFA)"),
            subtitle: _t(`Client: ${partner.name} | Solde actuel: ${pointsDisplay} pts`),
            startingValue: String(currentRendu),
        });

        // Allow 0 as valid value to reset the rendu monnaie
        // result is false/undefined only when popup is cancelled (Ignorer button)
        if (result !== false && result !== undefined && result !== null) {
            const amount = parseFloat(result) || 0;
            order.set_rendu_monnaie(amount);
            console.log("✅ Rendu monnaie set on order:", amount, "(Points will be updated on payment validation)");
        } else {
            console.log("ℹ️ Rendu monnaie cancelled");
        }
    },
});

patch(PosOrder.prototype, {
    setup() {
        super.setup(...arguments);
        this.rendu_monnaie = this.rendu_monnaie || 0;
        this.initial_loyalty_balance = this.initial_loyalty_balance ?? null;
        this.initial_loyalty_spent = this.initial_loyalty_spent ?? null;
        this.initial_loyalty_won = this.initial_loyalty_won ?? null;
        this.initial_loyalty_payment = this.initial_loyalty_payment ?? 0;
    },
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.rendu_monnaie = this.rendu_monnaie;

        // Capture loyalty state for JSON serialization (used for reprints).
        // postProcessLoyalty sets initial_loyalty_spent/won on the order object (for immediate receipt).
        // Here we also try to capture, with two passes:
        //   1. If balance not yet captured → first export, capture everything.
        //   2. If balance already captured → only update spent/won if getLoyaltyPoints shows > 0
        //      (avoids overwriting a valid spent with 0 from a post-clearing export).
        try {
            const stats = this.getLoyaltyPoints?.() || [];
            const stat = stats.find(s => s.program?.program_type === 'loyalty');
            if (stat) {
                if (this.initial_loyalty_balance === null || this.initial_loyalty_balance === undefined) {
                    this.initial_loyalty_balance = stat.points.balance;
                    this.initial_loyalty_spent  = stat.points.spent  ?? 0;
                    this.initial_loyalty_won    = stat.points.won    ?? 0;
                    console.log('[LOYALTY export] First capture → balance:', stat.points.balance,
                        '| won:', stat.points.won, '| spent:', stat.points.spent);
                } else if ((stat.points.spent ?? 0) > 0) {
                    // Balance already set but reward was applied after first capture — update spent/won.
                    this.initial_loyalty_spent = stat.points.spent;
                    this.initial_loyalty_won   = stat.points.won ?? 0;
                    console.log('[LOYALTY export] Updated spent:', stat.points.spent, '| won:', stat.points.won);
                }
            } else {
                console.log('[LOYALTY export] aucune stat fidélité. Stats:', stats);
            }
        } catch (e) {
            console.error('[LOYALTY export] Erreur:', e);
        }
        json.initial_loyalty_balance  = this.initial_loyalty_balance  ?? null;
        json.initial_loyalty_spent    = this.initial_loyalty_spent    ?? 0;
        json.initial_loyalty_won      = this.initial_loyalty_won      ?? 0;
        json.initial_loyalty_payment  = this.initial_loyalty_payment  ?? 0;
        return json;
    },
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.rendu_monnaie            = json.rendu_monnaie            || 0;
        this.initial_loyalty_balance  = json.initial_loyalty_balance  ?? null;
        this.initial_loyalty_spent    = json.initial_loyalty_spent    ?? null;
        this.initial_loyalty_won      = json.initial_loyalty_won      ?? null;
        this.initial_loyalty_payment  = json.initial_loyalty_payment  ?? 0;
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
