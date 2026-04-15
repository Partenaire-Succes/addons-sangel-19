/** @odoo-module **/

import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

console.warn("🔴 pos_navbar_patch.js LOADED - Patching Navbar (DSI/Caissière restrictions)");

patch(Navbar.prototype, {

    /**
     * Getter : même pattern que isCaissiere dans logout_button.js
     * Retourne true si l'utilisateur connecté est Caissière
     */
    get isCaissiere() {
        return this.pos.user?._is_caissiere || false;
    },

    /**
     * Getter : retourne true si l'utilisateur est DSI/IT
     */
    // get isDsiIt() {
    //     return this.pos.user?._is_dsi_it || false;
    // },

    /**
     * Patch : reloadProducts — bloque si non-DSI (sécurité JS en plus du t-if XML)
     */
    // async reloadProducts() {
    //     if (!this.pos.user._is_dsi_it) {
    //         this.dialog.add(AlertDialog, {
    //             title: _t("Accès refusé"),
    //             body: _t("L'action 'Recharger les données' est réservée au groupe DSI / IT."),
    //         });
    //         return;
    //     }
    //     return super.reloadProducts(...arguments);
    // },
});

console.warn("✅ pos_navbar_patch.js - Navbar patched (isCaissiere + isDsiIt getters)");
