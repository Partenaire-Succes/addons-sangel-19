/** @odoo-module */

import { OrderDisplay } from "@point_of_sale/app/components/order_display/order_display";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { patch } from "@web/core/utils/patch";

console.log("🔵 loyalty_single_line.js LOADED");

// ─── Patch 1 : OrderDisplay ───────────────────────────────────────────────────
// Cache les reward lines "discount produit spécifique" en mode display (caisse).
// Elles restent dans order.lines → comptabilité intacte.
// En mode receipt (ticket imprimé) : les 2 lignes restent visibles.

patch(OrderDisplay.prototype, {
    get comboSortedLines() {
        const allLines = this.order.lines.reduce((acc, line) => {
            if (line.combo_line_ids?.length > 0) {
                acc.push(line, ...line.combo_line_ids);
            } else if (!line.combo_parent_id) {
                acc.push(line);
            }
            return acc;
        }, []);

        if (this.props.mode === "receipt") {
            return allLines;
        }

        return allLines.filter((line) => {
            if (!line.is_reward_line) return true;
            const r = line.reward_id;
            return !(r && r.reward_type === "discount" && r.discount_applicability === "specific");
        });
    },
});

// ─── Patch 2 : Orderline ──────────────────────────────────────────────────────
// Getters réactifs sur le composant Orderline.
// OWL 2 track automatiquement l'accès à this.line.order_id.lines lors du rendu
// → re-render automatique quand une reward line est ajoutée/supprimée.

patch(Orderline.prototype, {

    /**
     * Cherche la reward line "discount spécifique" liée à cette ligne produit.
     * Retourne null si aucune reward de ce type ne correspond.
     */
    get _loyaltyRewardLine() {
        const line = this.line;
        if (!line || line.is_reward_line) return null;
        const allLines = line.order_id?.lines;
        if (!allLines?.length) return null;
        return allLines.find((rl) => {
            if (!rl.is_reward_line) return false;
            const reward = rl.reward_id;
            if (!reward || reward.reward_type !== "discount") return false;
            if (reward.discount_applicability !== "specific") return false;
            const targetIds = (reward.reward_product_ids || []).map((p) =>
                p !== null && typeof p === "object" ? p.id : p
            );
            return targetIds.includes(line.product_id?.id);
        }) || null;
    },

    /**
     * Prix net après remise loyalty.
     * Ex : $1.38 (produit) + (-$0.21) (reward) = $1.17 (net)
     * Retourne null si aucune reward associée.
     */
    get loyaltyNetPrice() {
        const rl = this._loyaltyRewardLine;
        if (!rl) return null;
        return this.line.getPriceWithTax() + rl.getPriceWithTax();
    },

    /**
     * Description du programme de remise (nom affiché en sous-texte).
     */
    get loyaltyDescription() {
        const rl = this._loyaltyRewardLine;
        if (!rl) return null;
        return rl.reward_id?.description || rl.full_product_name || "";
    },

});

console.log("✅ loyalty_single_line.js — patches appliqués");
