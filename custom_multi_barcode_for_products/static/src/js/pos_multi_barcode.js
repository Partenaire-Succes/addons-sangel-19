/** @odoo-module **/

import { Product } from "@point_of_sale/app/models/product";
import { patch } from "@web/core/utils/patch";
console.log("ALEXANDRE PATCH");
patch(Product.prototype, {
    setup() {
        super.setup(...arguments);

        // Ajouter les barcodes secondaires dans l'index du POS
        if (this.secondary_barcodes && this.secondary_barcodes.length) {
            this.secondary_barcodes.forEach((barcode) => {
                this.pos.barcodeReader.add_barcode(barcode, this);
            });
        }
    },

    // Ajouter la recherche par code barre secondaire
    custom_scan_product(code) {
        const product = this.pos.db.get_product_by_barcode(code);
        if (product) {
            return product;
        }
        return super.custom_scan_product(code);
    },

    // Ajouter la recherche par code barre principale
    custom_scan_product_by_barcode(code) {
        if (this.barcode === code) {
            return this;
        }
        return super.custom_scan_product_by_barcode(code);
    },
});
