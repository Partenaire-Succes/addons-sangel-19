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
        if (confirmed) {
            window.location.href = "/web/session/logout?redirect=/web/login";
        }
    },

});
