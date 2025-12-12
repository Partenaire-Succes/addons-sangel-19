/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { rpc } from "@web/core/network/rpc";

/** Calcule la quantité totale d’un produit dans la commande */
function getTotalQtyForProduct(order, product) {
    return order.get_orderlines()
        .filter(l => l.get_product()?.id === product.id && !l.is_reward_line && !l.promo_for_product_id)
        .reduce((sum, l) => sum + l.get_quantity(), 0);
}

/** Sérialise les lots en objets simples */
function serializeLots(pack_lot_ids) {
    return (Array.isArray(pack_lot_ids) ? pack_lot_ids : []).map(l => ({
        id: l.id,
        lot_name: l.lot_name,
        qty: 1,
    }));
}

/** Ajoute/supprime la ligne promo 3=4 */
async function upsertPromoLine(store, order, product, contextLabel) {
    if (!order || !product) return;

    const totalQty = getTotalQtyForProduct(order, product);
    const allLots = [];
    order.get_orderlines()
        .filter(l => l.get_product()?.id === product.id && !l.is_reward_line && !l.promo_for_product_id)
        .forEach(l => allLots.push(...serializeLots(l.pack_lot_ids)));

    let result;
    try {
        result = await rpc("/pos_promo/check_3x4", {
            product_id: product.id,
            qty: totalQty,
            lot_lines: allLots,
        });
    } catch (err) {
        console.error("[3x4] RPC error:", err);
        return;
    }

    // Supprimer anciennes lignes promo
    const oldPromoLines = order.get_orderlines().filter(l => l.promo_for_product_id === product.id);
    oldPromoLines.forEach(line => order.deleteOrderline(line));

    if (result?.apply) {
        // Ajout via le store
        await store.addLineToOrder({
            order_id: order,
            product_id: product,
            qty: 1,
            price_unit: -result.discount_amount,
            price_type: "manual",
            tax_ids: product.taxes_id.map(t => ["link", t]),
        }, order, {});

        const promo_line = order.get_orderlines().at(-1);
        promo_line.set_full_product_name(`Promo 3=4 (${result.free_qty} offert)`);
        promo_line.promo_for_product_id = product.id;
    }
}

/** Patch: ajout initial */
const superAddLineToCurrentOrder = PosStore.prototype.addLineToCurrentOrder;
patch(PosStore.prototype, {
    async addLineToCurrentOrder(vals, opts) {
        const res = await superAddLineToCurrentOrder.call(this, vals, opts);
        const order = this.get_order();
        const product = vals?.product_id;
        if (order && product) {
            await upsertPromoLine(this, order, product, "addLineToCurrentOrder"); // ✅ store passé
        }
        return res;
    },
});

/** Patch: modification de quantité */
const superSetQuantity = PosOrderline.prototype.set_quantity;
patch(PosOrderline.prototype, {
    set_quantity(quantity, keep_price) {
        const res = superSetQuantity.call(this, quantity, keep_price);
        const product = this.get_product();
        const order = this.order_id;
        if (product && order && !this.is_reward_line && !this.promo_for_product_id) {
            upsertPromoLine(this.models.pos, order, product, "set_quantity"); // ✅ store passé
        }
        return res;
    },
});

/** Patch: sélection de lots */
const superSetPackLotLines = PosOrderline.prototype.setPackLotLines;
patch(PosOrderline.prototype, {
    setPackLotLines(args) {
        const res = superSetPackLotLines.call(this, args);
        const product = this.get_product();
        const order = this.order_id;
        if (product && order && !this.is_reward_line && !this.promo_for_product_id) {
            upsertPromoLine(this.models.pos, order, product, "setPackLotLines"); // ✅ store passé
        }
        return res;
    },
});
