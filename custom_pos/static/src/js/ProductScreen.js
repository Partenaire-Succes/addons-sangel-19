/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

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
        // IMPORTANT: is_reward_line est sur la LIGNE, pas sur le produit
        orderLines.forEach(line => {
            if (!line) return;
            const product = line.product_id;
            // is_reward_line est sur la ligne, price_unit contient le prix
            if (line.is_reward_line || (line.price_unit !== undefined && line.price_unit < 0)) {
                if (product) {
                    promoProducts.set(product.id, {
                        name: product.display_name
                    });
                }
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

        // ========== Détection des remises MANUELLES uniquement ==========
        // Seules les remises manuelles (discount > 0 sur la ligne) nécessitent un code d'accès
        // Les lignes de récompense Odoo (via "Saisir un code" natif) ne nécessitent PAS de code d'accès
        
        // Type 1: Remise manuelle sur la ligne (discount > 0) - NÉCESSITE code d'accès
        const hasManualLineDiscount = orderLines.some(line => line && line.discount > 0);

        // Collecter les infos des produits avec remise manuelle pour affichage dans le popup
        const discountedProducts = [];
        orderLines.forEach(line => {
            if (line && line.discount > 0) {
                const product = line.product_id;
                if (product) {
                    const code = product.default_code || product.barcode || '';
                    discountedProducts.push({
                        code: code,
                        name: product.name,  // Utiliser name (pas display_name qui inclut déjà le code)
                        discount: line.discount
                    });
                }
            }
        });

        // Type 2: Ligne de récompense Odoo (is_reward_line ou price_unit négatif) - NE nécessite PAS de code
        // Ces lignes proviennent du workflow natif Odoo (Actions → Saisir un code)
        // IMPORTANT: is_reward_line est sur la LIGNE, pas sur le produit!
        const hasOdooRewardLine = orderLines.some(line => {
            if (!line) return false;
            // is_reward_line est une propriété de la ligne (pas du produit)
            return line.is_reward_line || (line.price_unit !== undefined && line.price_unit < 0);
        });

        // Seules les remises MANUELLES déclenchent la demande de code d'accès
        const hasDiscount = hasManualLineDiscount;

        console.log("Remise manuelle sur ligne:", hasManualLineDiscount);
        console.log("Ligne de récompense Odoo:", hasOdooRewardLine);
        console.log("Code d'accès requis:", hasDiscount);

        // ========== Stock et code d'accès ==========
        // IMPORTANT: Exclure les lignes de récompense Odoo du contrôle de stock
        // (elles sont virtuelles et n'ont pas de stock)
        const product_ids = orderLines
            .filter(line => {
                if (!line || !line.product_id) return false;
                // Exclure les lignes de récompense Odoo (is_reward_line est sur la LIGNE)
                if (line.is_reward_line) return false;
                // Exclure les lignes avec prix négatif (réductions)
                if (line.price_unit !== undefined && line.price_unit < 0) return false;
                return true;
            })
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
                const codeInput = await this._showPasswordPrompt(result.message, discountedProducts);
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

    async _showPasswordPrompt(message, discountedProducts = []) {
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
            box.style.maxWidth = "500px";

            const title = document.createElement("h3");
            title.innerText = "🔐 Code d'accès requis";
            box.appendChild(title);

            const msg = document.createElement("p");
            msg.innerText = message;
            box.appendChild(msg);

            // Afficher la liste des produits avec remises manuelles
            if (discountedProducts.length > 0) {
                const discountSection = document.createElement("div");
                discountSection.style.marginTop = "10px";
                discountSection.style.marginBottom = "10px";

                const discountTitle = document.createElement("p");
                discountTitle.style.fontWeight = "bold";
                discountTitle.style.marginBottom = "5px";
                discountTitle.innerText = "Produits avec remise :";
                discountSection.appendChild(discountTitle);

                discountedProducts.forEach(p => {
                    const line = document.createElement("p");
                    line.style.margin = "2px 0";
                    line.style.paddingLeft = "10px";
                    const codeDisplay = p.code ? `[${p.code}] ` : '';
                    line.innerText = `• ${codeDisplay}${p.name} (${p.discount}%)`;
                    discountSection.appendChild(line);
                });

                box.appendChild(discountSection);
            }

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