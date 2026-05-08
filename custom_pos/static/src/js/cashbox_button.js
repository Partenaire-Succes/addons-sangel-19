/** @odoo-module **/
/**
 * Ouverture manuelle du tiroir caisse — ProductScreen, raccourci Alt+C.
 *
 * Deux chemins selon la configuration Odoo :
 *
 *  1. hardwareProxy.printer est disponible (iface_print_via_proxy ou other_devices)
 *     → openCashbox() direct, aucune impression papier.
 *
 *  2. hardwareProxy.printer est null (USB Windows sans config proxy)
 *     → Impression d'un ticket "TIROIR CAISSE" dans une popup.
 *     → Le driver Windows EPSON ouvre le tiroir sur chaque impression,
 *       exactement comme lors d'un ticket de vente.
 *     → Aucune configuration Odoo supplémentaire nécessaire.
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
        // ── Chemin 1 : proxy/ePOS Odoo natif ───────────────────────────────
        if (this.hardwareProxy.printer) {
            try {
                await this.hardwareProxy.printer.openCashbox();
                this.notification.add(_t("Caisse ouverte."), { type: "success" });
            } catch (e) {
                this.notification.add(_t("Erreur ouverture caisse."), { type: "danger", sticky: true });
            }
            return;
        }

        // ── Chemin 2 : impression ticket minimal ───────────────────────────
        // Le driver Windows EPSON ouvre le tiroir sur chaque impression.
        // On utilise une popup isolée pour ne pas imprimer l'écran POS.
        this._printCashboxSlip();
    },

    _printCashboxSlip() {
        // Iframe invisible dans la page courante — aucun nouvel onglet
        const iframe = document.createElement("iframe");
        iframe.style.cssText =
            "position:fixed;width:0;height:0;border:none;left:-9999px;top:-9999px;visibility:hidden;";
        document.body.appendChild(iframe);

        const now   = new Date();
        const heure = now.toLocaleTimeString("fr-FR", {
            hour: "2-digit", minute: "2-digit", second: "2-digit",
        });
        const caisse = this.pos.config.name || "";

        const doc = iframe.contentDocument || iframe.contentWindow.document;

        doc.head.innerHTML =
            '<meta charset="utf-8"/>' +
            "<style>" +
            "* { margin:0; padding:0; box-sizing:border-box; }" +
            'body { font-family:"Courier New",monospace; font-size:12px;' +
            "       text-align:center; padding:6px 10px; width:72mm; }" +
            ".sep  { border-top:1px dashed #000; margin:5px 0; }" +
            ".bold { font-weight:bold; font-size:13px; letter-spacing:1px; }" +
            ".sm   { font-size:11px; color:#333; }" +
            "</style>";

        doc.body.innerHTML =
            '<div class="sep"></div>' +
            '<div class="bold">--- OUVERTURE TIROIR CAISSE ---</div>' +
            "<div>" + heure + "</div>" +
            (caisse ? '<div class="sm">' + caisse + "</div>" : "") +
            '<div class="sep"></div>';

        // Laisser le navigateur terminer le rendu avant d'imprimer
        setTimeout(() => {
            iframe.contentWindow.focus();
            iframe.contentWindow.print();

            // Nettoyer l'iframe une fois l'impression envoyée
            const cleanup = () => {
                try { document.body.removeChild(iframe); } catch (_) {}
            };
            iframe.contentWindow.addEventListener("afterprint", cleanup);
            setTimeout(cleanup, 3000); // Fallback si afterprint non supporté
        }, 100);

        this.notification.add(_t("Caisse ouverte."), { type: "success" });
    },
});
