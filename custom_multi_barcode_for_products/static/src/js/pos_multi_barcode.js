/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";

/**
 * Patch _getProductByBarcode pour chercher aussi dans les codes-barres
 * secondaires (product.multiple.barcodes).
 *
 * Le champ `secondary_barcodes` est injecté par Python dans
 * product_product._load_pos_data() sous forme de tableau de chaînes.
 *
 * is_active_barcode n'est PAS touché ici (gère l'impression étiquette).
 */
patch(ProductScreen.prototype, {
    async _getProductByBarcode(code) {
        // Étape 1 : comportement natif intact (barcode principal + packaging + RPC fallback)
        const product = await super._getProductByBarcode(...arguments);
        if (product) {
            return product;
        }

        // Étape 2 : recherche dans les codes-barres secondaires chargés en mémoire
        // _secondary_barcodes (préfixe _ = getter auto créé par Odoo 18/19, cf. index.js)
        const barcode = code.base_code;
        const allProducts = this.pos.models["product.product"].getAll();
        for (const p of allProducts) {
            const barcodes = p._secondary_barcodes;
            if (barcodes && barcodes.includes(barcode)) {
                return p;
            }
        }

        return null;
    },
});
