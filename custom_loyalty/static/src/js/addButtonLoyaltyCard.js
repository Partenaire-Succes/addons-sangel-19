/** @odoo-module **/

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
    },

    async onClickLoyalty() {
        const order = this.pos.getOrder();
        if (!order) {
            this.dialog.add(AlertDialog, {
                title: _t("Aucun client"),
                body: _t("Veuillez sélectionner un client d'abord."),
            });
            return;
        }

        const partner = order.getPartner();
        if (!partner) {
            this.dialog.add(AlertDialog, {
                title: _t("Aucun client"),
                body: _t("Veuillez sélectionner un client d'abord."),
            });
            return;
        }

        const posId = this.pos.config && this.pos.config.id ? this.pos.config.id : false;
        const posName = this.pos.config && this.pos.config.name ? this.pos.config.name : "";
        const timestamp = new Date().toISOString().slice(0, 19).replace('T', ' ');
        const posNameTime = `Caisse ${posName} - ${timestamp}`;

        this.env.services.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'update.loyalty.card.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_partner_id: partner.id,
                default_pos_id: posId,
                default_points: 0.0,
                default_pos_name: posNameTime,
            },
        });
    }
});