/** @odoo-module **/
/**
 * Bouton d'ouverture manuelle de la caisse sur le ProductScreen.
 * Ajoute :
 *   - un bouton "Ouvrir la caisse" visible dans la zone de contrôle principale
 *   - le même bouton dans le popup "..." (pour mobile/petits écrans)
 *   - raccourci clavier Alt+C
 *
 * Fonctionnement : appelle directement printer.openCashbox() en contournant la
 * garde iface_cashdrawer de hardwareProxy.openCashbox(), ce qui garantit le même
 * chemin que l'impression de ticket (HWPrinter ou IoTPrinter).
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

        /**
         * POURQUOI on n'utilise plus hardwareProxy.openCashbox() :
         *
         * Cette méthode native contient 3 gardes silencieuses :
         *   1. iface_cashdrawer doit être activé dans la config POS
         *   2. hardwareProxy.printer doit être non null
         *   3. connectionInfo.status doit être "connected" ou "init"
         *
         * Si l'une d'elles est fausse → rien ne se passe, pas d'erreur,
         * et l'ancienne notification "Signal envoyé" s'affichait quand même.
         *
         * SOLUTION : on appelle hardwareProxy.printer.openCashbox() directement,
         * le même chemin exact qu'une impression de ticket :
         *   HWPrinter  → POST /hw_proxy/default_printer_action  { action:"cashbox" }
         *   IoTPrinter → device.action({ action:"cashbox" })  via IoT longpolling
         */
        const printer = this.hardwareProxy.printer;

        if (!printer) {
            // Le proxy n'a pas de printer : iface_print_via_proxy probablement désactivé
            console.warn("[CAISSE] hardwareProxy.printer est null — proxy non connecté ou iface_print_via_proxy désactivé");
            this.notification.add(
                _t("Impossible d'ouvrir la caisse : l'imprimante n'est pas connectée au proxy."),
                { type: "warning", sticky: true }
            );
            return;
        }

        try {
            await printer.openCashbox();
            console.log("[CAISSE] Caisse ouverte avec succès.");
            this.notification.add(
                _t("Caisse ouverte."),
                { type: "success", sticky: false }
            );
        } catch (error) {
            console.error("[CAISSE] Erreur lors de l'ouverture :", error);
            this.notification.add(
                _t("Échec ouverture caisse : vérifiez la connexion à l'imprimante."),
                { type: "danger", sticky: true }
            );
        }
    },
});
