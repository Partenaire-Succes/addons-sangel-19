/** @odoo-module **/
/**
 * Ouverture manuelle du tiroir caisse depuis le ProductScreen.
 * Raccourci clavier : Alt+C
 *
 * Utilise exactement le même chemin qu'une validation de paiement :
 *   this.hardwareProxy.printer.openCashbox()
 * Ce chemin est déjà opérationnel (le tiroir s'ouvre à chaque vente).
 * On le réutilise, sans aucune infrastructure supplémentaire.
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

        useHotkey("alt+c", () => this.openCashboxManual(), {
            bypassEditableProtection: true,
        });
    },

    async openCashboxManual() {
        const printer = this.hardwareProxy.printer;

        if (!printer) {
            // Ce message ne devrait jamais apparaître si iface_cashdrawer est activé
            // et que l'imprimante est bien configurée dans les réglages POS.
            this.notification.add(
                _t("Imprimante non connectée — vérifiez les réglages POS (Tiroir caisse activé ?)"),
                { type: "warning", sticky: true }
            );
            return;
        }

        try {
            await printer.openCashbox();
            this.notification.add(_t("Caisse ouverte."), { type: "success" });
        } catch (err) {
            console.error("[CAISSE] Erreur ouverture :", err);
            this.notification.add(
                _t("Erreur lors de l'ouverture de la caisse."),
                { type: "danger", sticky: true }
            );
        }
    },
});
