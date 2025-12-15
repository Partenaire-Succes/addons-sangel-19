import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosStore.prototype, {
    async after_load_server_data() {
        await super.after_load_server_data();
        // Récupère uniquement les promos actives et valides
        this.promotions = await this.orm.call("pos.promotion", "get_active_promotions", []);
        console.log("[POS Promotion] Promotions chargées :", this.promotions);
    },
});

patch(PosOrder.prototype, {
    addProduct(product, options = {}) {
        console.log("[POS Promotion] Produit ajouté :", product.display_name, "Options:", options);

        const res = super.addProduct(product, options);

        if (options && options.is_free) {
            console.log("[POS Promotion] Ligne gratuite détectée, on ne relance pas la promo.");
            return res;
        }

        const promotions = this.pos.promotions || [];
        if (!promotions.length) {
            console.log("[POS Promotion] Aucune promotion active.");
            return res;
        }

        const sumQtyForProduct = (productId) => {
            let qty = 0;
            for (const line of this.getOrderlines()) {
                if (line.product.id === productId && !line.getUserData()?.is_free) {
                    qty += line.getQuantity();
                }
            }
            return qty;
        };

        const addFreeLine = (freeProduct, qty) => {
            console.log("[POS Promotion] Ajout d'une ligne gratuite :", freeProduct.display_name, "Quantité:", qty);
            const line = super.addProduct(freeProduct, { quantity: qty, price: 0, is_free: true });
            const lastLine = this.getOrderlines().slice(-1)[0];
            lastLine.setUnitPrice(0);
            lastLine.setUserData({ ...(lastLine.getUserData() || {}), is_free: true });
            return line;
        };

        for (const promo of promotions) {
            const productIds = new Set((promo.product_ids || []).map((p) => p));
            if (!productIds.has(product.id)) continue;

            console.log("[POS Promotion] Promo trouvée :", promo.name, "Buy:", promo.buy_qty, "Free:", promo.free_qty);

            const qtyOnThisProduct = sumQtyForProduct(product.id);
            console.log("[POS Promotion] Quantité totale sur", product.display_name, ":", qtyOnThisProduct);

            const blocks = Math.floor(qtyOnThisProduct / promo.buy_qty);
            console.log("[POS Promotion] Nombre de blocs complets :", blocks);

            let alreadyFree = 0;
            for (const line of this.getOrderlines()) {
                if (line.product.id === product.id && line.getUserData()?.is_free) {
                    alreadyFree += line.getQuantity();
                }
            }
            console.log("[POS Promotion] Déjà offert :", alreadyFree);

            const toGive = blocks * promo.free_qty - alreadyFree;
            console.log("[POS Promotion] Quantité gratuite à ajouter :", toGive);

            if (toGive > 0) {
                addFreeLine(product, toGive);
            }
        }

        return res;
    },
});
