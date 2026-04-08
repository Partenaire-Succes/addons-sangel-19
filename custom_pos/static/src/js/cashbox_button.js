/** @odoo-module **/
/**
 * Bouton d'ouverture manuelle de la caisse sur le ProductScreen.
 * Ajoute :
 *   - un bouton "Ouvrir la caisse" visible dans la zone de contrôle principale
 *   - le même bouton dans le popup "..." (pour mobile/petits écrans)
 *   - raccourci clavier Alt+C
 *
 * Nécessite : POS Config → Hardware → Cashdrawer activé (iface_cashdrawer = true)
 */
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.hardwareProxy = useService("hardware_proxy");

        // Raccourci clavier Alt+C — fonctionne depuis le ProductScreen
        useHotkey(
            "alt+c",
            () => this.openCashboxManual(),
            { bypassEditableProtection: true }
        );
    },

    async openCashboxManual() {
        console.log("[CAISSE] Tentative d'ouverture manuelle...");
        try {
            const result = await this.hardwareProxy.openCashbox(_t("Ouverture manuelle"));
            console.log("[CAISSE] Réponse hardwareProxy.openCashbox :", result);
            this.notification.add(
                _t("Signal d'ouverture envoyé à la caisse."),
                { type: "success", sticky: false }
            );
        } catch (error) {
            console.error("[CAISSE] Erreur lors de l'ouverture :", error);
            this.notification.add(
                _t("Échec ouverture caisse : ") + (error?.message || error),
                { type: "danger", sticky: false }
            );
        }
    },
});
