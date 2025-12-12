/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { rpc } from "@web/core/network/rpc";

patch(PosStore.prototype, {
    async pay() {
        const currentOrder = this.getOrder();
        const orderLines = currentOrder.getOrderlines();

        // ========== Quantité nulle ==========
        const hasZeroQty = orderLines.some(line => line && line.qty === 0);
        if (hasZeroQty) {
            this.dialog.add(AlertDialog, {
                title: _t("Quantité nulle non autorisée"),
                body: _t("Seules les quantités positives sont autorisées pour confirmer la commande."),
            });
            return;
        }

        // ========== Double remise interdite ==========
        const productsWithLineDiscount = new Map();
        const promoProducts = new Map();
        const doubleDiscountProducts = [];

        // Collecter les produits avec remise sur ligne
        orderLines.forEach(line => {
            if (line && line.discount > 0) {
                const product = line.product_id;
                if (product) {
                    productsWithLineDiscount.set(product.id, {
                        name: product.display_name,
                        discount: line.discount
                    });
                }
            }
        });

        // Collecter les produits avec ligne de promotion
        orderLines.forEach(line => {
            if (!line) return;
            const product = line.product_id;
            if (product && (line.price < 0 || product.is_reward_line)) {
                promoProducts.set(product.id, {
                    name: product.display_name
                });
            }
        });

        // Vérifier et collecter les produits avec double remise
        productsWithLineDiscount.forEach((productInfo, productId) => {
            if (promoProducts.has(productId)) {
                doubleDiscountProducts.push({
                    name: productInfo.name,
                    discount: productInfo.discount
                });
            }
        });

        if (doubleDiscountProducts.length > 0) {
            const productList = doubleDiscountProducts
                .map(p => `   • ${p.name} (${p.discount}% de remise ligne)`)
                .join('\n');
            
            this.dialog.add(AlertDialog, {
                title: _t("❌ Double remise interdite"),
                body: _t(`Les produits suivants ont à la fois une remise sur la ligne ET une promotion :\n\n${productList}\n\nVeuillez supprimer l'une des deux remises avant de continuer.`),
            });
            return;
        }

        // ========== Détection des remises ==========
        // Type 1: Remise sur la ligne (discount > 0)
        const hasLineDiscount = orderLines.some(line => line && line.discount > 0);
        
        // Type 2: Ligne de remise/promotion (prix négatif ou programme promo)
        const hasPromoLine = orderLines.some(line => {
            if (!line) return false;
            const product = line.product_id;
            return line.price < 0 || 
                   (product && product.is_reward_line) ||
                   (product && product.name && product.name.toLowerCase().includes('remise'));
        });

        const hasDiscount = hasLineDiscount || hasPromoLine;

        console.log("Remise sur ligne:", hasLineDiscount);
        console.log("Ligne de promotion:", hasPromoLine);
        console.log("A une remise:", hasDiscount);

        // ========== Stock et code d'accès ==========
        const product_ids = orderLines
            .filter(line => line && line.product_id)
            .map(line => line.product_id.id);

        if (!product_ids.length) {
            return super.pay(...arguments);
        }

        const result = await rpc("/web/dataset/call_kw/pos.order/check_stock_levels", {
            model: "pos.order",
            method: "check_stock_levels",
            args: [product_ids, hasDiscount],
            kwargs: {},
        });
        
        console.log("Résultat vérification:", result);
        
        if (result.error) {
            if (result.access_required && result.code_acces) {
                const codeInput = await this._showPasswordPrompt(result.message);
                if (codeInput !== result.code_acces) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Code incorrect"),
                        body: _t("Le code saisi est invalide. La vente est annulée."),
                    });
                    return;
                }
            } else {
                this.dialog.add(AlertDialog, {
                    title: _t("Stock indisponible"),
                    body: _t(result.message),
                });
                return;
            }
        }

        return super.pay(...arguments);
    },

    async _showPasswordPrompt(message) {
        return new Promise((resolve) => {
            const overlay = document.createElement("div");
            overlay.style.position = "fixed";
            overlay.style.top = "0";
            overlay.style.left = "0";
            overlay.style.width = "100%";
            overlay.style.height = "100%";
            overlay.style.background = "rgba(0,0,0,0.5)";
            overlay.style.zIndex = "9999";
            overlay.style.display = "flex";
            overlay.style.alignItems = "center";
            overlay.style.justifyContent = "center";

            const box = document.createElement("div");
            box.style.background = "#fff";
            box.style.padding = "20px";
            box.style.borderRadius = "8px";
            box.style.boxShadow = "0 0 10px rgba(0,0,0,0.3)";
            box.style.minWidth = "300px";

            const title = document.createElement("h3");
            title.innerText = "🔐 Code d'accès requis";
            box.appendChild(title);

            const msg = document.createElement("p");
            msg.innerText = message;
            box.appendChild(msg);

            const input = document.createElement("input");
            input.type = "password";
            input.placeholder = "Entrez le code";
            input.style.width = "100%";
            input.style.marginBottom = "10px";
            box.appendChild(input);

            const btnRow = document.createElement("div");
            btnRow.style.textAlign = "right";

            const cancelBtn = document.createElement("button");
            cancelBtn.innerText = "Annuler";
            cancelBtn.style.marginRight = "10px";
            cancelBtn.onclick = () => {
                document.body.removeChild(overlay);
                resolve(null);
            };

            const okBtn = document.createElement("button");
            okBtn.innerText = "Valider";
            okBtn.onclick = () => {
                const value = input.value;
                document.body.removeChild(overlay);
                resolve(value);
            };

            btnRow.appendChild(cancelBtn);
            btnRow.appendChild(okBtn);
            box.appendChild(btnRow);
            overlay.appendChild(box);
            document.body.appendChild(overlay);
            input.focus();
        });
    },

    getReceiptHeaderData(order) {
        const result = super.getReceiptHeaderData(order);
        result.pos_config_name = this.config.name;
        return result;
    }
});