/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { LoginScreen } from "@point_of_sale/app/screens/login_screen/login_screen";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

patch(LoginScreen.prototype, {

    setup() {
        super.setup();
        this.dialog = useService("dialog");
    },

    get isCaissiere() {
        return this.pos.user?._is_caissiere || false;
    },

    async confirmLogout() {
        const confirmed = await ask(this.dialog, {
            title: _t("Confirmation"),
            body: _t("Voulez-vous vraiment vous déconnecter d'Odoo ?"),
            confirmLabel: _t("Déconnexion"),
            cancelLabel: _t("Annuler"),
        });
        if (!confirmed) {
            return;
        }
        // Si une nouvelle session a été créée en état "opening_control" suite au
        // rechargement du POS (router.close), on la supprime côté backend avant
        // de quitter, pour éviter qu'elle réapparaisse au prochain chargement.
        try {
            if (this.pos.session && this.pos.session.state === "opening_control") {
                await this.pos.data.call(
                    "pos.session",
                    "delete_opening_control_session",
                    [this.pos.session.id]
                );
            }
        } catch (e) {
            // Ne bloque pas la déconnexion si l'appel échoue
            console.warn("delete_opening_control_session:", e);
        }
        window.location.href = "/web/session/logout?redirect=/web/login";
    },

});
