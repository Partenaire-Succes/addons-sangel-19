/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";

patch(OpeningControlPopup.prototype, {
    setup() {
        super.setup();
        console.log("Custom OpeningControlPopup setup Test");
        this.state.openingCash = this.env.utils.formatCurrency(100000, false);
    },
});