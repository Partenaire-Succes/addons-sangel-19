/** @odoo-module */

import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { patch } from "@web/core/utils/patch";

// Patch Orderline component to accept lineNumber prop
patch(Orderline, {
    props: {
        ...Orderline.props,
        lineNumber: { type: Number, optional: true },
    },
});
