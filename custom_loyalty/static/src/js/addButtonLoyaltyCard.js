/** @odoo-module **/

import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
    },

    async onClickLoyalty() {
    const order = this.pos.get_order();
    const partner = order.get_partner();
    const pos_id = this.pos.config.id;

    if (!partner) {
        this.dialog.add(AlertDialog, {
            title: _t("Aucun client"),
            body: _t("Veuillez sélectionner un client d'abord."),
        });
        return;
    }

    const posName = this.pos.config.name;
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
            default_pos_id: pos_id.id,
            default_points: 0.0,
            default_pos_name: posNameTime,
        },
    });
}
});