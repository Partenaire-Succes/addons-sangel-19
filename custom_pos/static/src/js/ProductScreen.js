/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { validateManagerCode } from "@custom_pos/js/pos_validation_utils";
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
        // Seules les remises manuelles nécessitent un code d'accès.
        // Les remises auto-appliquées (sale.promotion, remise partenaire) sont exclues
        // grâce aux flags _promoDiscountApplied et _globalDiscountApplied.

        // Type 1: Remise manuelle sur la ligne - NÉCESSITE code d'accès
        // Exclure les remises auto-appliquées par sale.promotion ou par la remise partenaire
        const hasManualLineDiscount = orderLines.some(line =>
            line &&
            line.discount > 0 &&
            !line._promoDiscountApplied &&
            !line._globalDiscountApplied
        );

        // Collecter les infos des produits avec remise MANUELLE pour affichage dans le popup
        const discountedProducts = [];
        orderLines.forEach(line => {
            if (line && line.discount > 0 && !line._promoDiscountApplied && !line._globalDiscountApplied) {
                const product = line.product_id;
                if (product) {
                    const code = product.default_code || product.barcode || '';
                    discountedProducts.push({
                        code: code,
                        name: product.name,
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

        // ========== Vérification réduction de prix ==========
        // Collecter les lignes avec prix modifié MANUELLEMENT (pour vérification backend).
        // Les prix issus d'une liste de prix (price_type !== "manual") sont exclus :
        // ils ont été définis par la configuration tarifaire, pas par la caissière.
        const priceReductionLines = [];
        orderLines.forEach(line => {
            if (!line || !line.product_id) return;
            if (line.is_reward_line) return;
            if (line.price_unit !== undefined && line.price_unit < 0) return;
            // Prix appliqué par une liste de prix → pas de code requis
            if (line.price_type !== "manual") return;

            const product = line.product_id;
            const originalPrice = product.lst_price;  // HT catalogue
            const currentPrice = line.price_unit;      // HT modifié

            // Facteur TTC : price_subtotal_incl / price_subtotal
            // Fonctionne que la taxe soit incluse ou non (si pas de taxe → facteur = 1)
            const taxFactor = (line.price_subtotal > 0)
                ? line.price_subtotal_incl / line.price_subtotal
                : 1;

            // Vérifier si le prix a été réduit
            if (currentPrice < originalPrice) {
                priceReductionLines.push({
                    product_id: product.id,
                    unit_price: currentPrice,               // HT → vérification backend
                    product_name: product.display_name,
                    original_price: originalPrice,          // HT → vérification backend
                    original_price_ttc: originalPrice * taxFactor,  // TTC → journal
                    unit_price_ttc: currentPrice * taxFactor,       // TTC → journal
                });
            }
        });

        console.log("Lignes avec réduction de prix:", priceReductionLines);

        // ========== Vérification réduction de prix (avant stock) ==========
        if (priceReductionLines.length > 0) {
            try {
                const priceResult = await rpc("/web/dataset/call_kw/pos.order/check_price_reduction", {
                    model: "pos.order",
                    method: "check_price_reduction",
                    args: [priceReductionLines],
                    kwargs: {},
                });
                
                console.log("Résultat vérification prix:", priceResult);
                
                if (priceResult.error && priceResult.access_required) {
                    const priceCodeInput = await this._showPasswordPrompt(priceResult.message, []);
                    const priceInfo = priceReductionLines.length > 0
                        ? priceReductionLines.map(p => ({
                            produit: p.product_name,
                            avant: p.original_price_ttc,
                            apres: p.unit_price_ttc,
                        }))
                        : null;
                    // Log différé : order.name (serveur) n'est disponible qu'après paiement
                    const { success: priceOk, managerId: priceMgrId } = await validateManagerCode(
                        priceCodeInput, "price_reduction", this,
                        "", priceResult.code_acces || null, null, false
                    );
                    if (!priceOk) {
                        this.dialog.add(AlertDialog, {
                            title: _t("Code incorrect"),
                            body: _t("Le code saisi est invalide. La vente est annulée."),
                        });
                        return;
                    }
                    if (!currentOrder._pendingLogs) currentOrder._pendingLogs = [];
                    currentOrder._pendingLogs.push({ manager_id: priceMgrId, action: "price_reduction", price_info: priceInfo });
                }
            } catch (error) {
                // Mode hors-ligne - vérification locale de réduction de prix
                console.warn("Mode hors-ligne détecté pour vérification prix:", error.message || error);
                
                // En mode hors-ligne, on utilise les données locales
                const accessCode = this.config.code_acces;
                
                if (priceReductionLines.length > 0) {
                    const productList = priceReductionLines
                        .map(p => `   • ${p.product_name}: ${p.original_price.toFixed(2)} → ${p.unit_price.toFixed(2)}`)
                        .join('\n');
                    
                    const message = `⚠️ Modification de prix détectée (mode hors-ligne) :\n\n${productList}\n\nUn code d'accès est requis pour valider cette réduction de prix.`;

                    if (accessCode) {
                        const codeInput = await this._showPasswordPrompt(message, []);
                        const offlinePriceInfo = priceReductionLines.length > 0
                            ? priceReductionLines.map(p => ({
                                produit: p.product_name,
                                avant: p.original_price_ttc,   // TTC catalogue
                                apres: p.unit_price_ttc,       // TTC modifié à la caisse
                            }))
                            : null;
                        const { success: offlinePriceOk } = await validateManagerCode(
                            codeInput, "price_reduction", this,
                            currentOrder?.name || "", accessCode, offlinePriceInfo
                        );
                        if (!offlinePriceOk) {
                            this.dialog.add(AlertDialog, {
                                title: _t("Code incorrect"),
                                body: _t("Le code saisi est invalide. La vente est annulée."),
                            });
                            return;
                        }
                    } else {
                        // Pas de code configuré, on laisse passer en mode hors-ligne
                        console.warn("Mode hors-ligne: Pas de code d'accès configuré pour réduction prix - vente autorisée");
                    }
                }
            }
        }

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

        // ========== Vérification stock avec gestion mode hors-ligne ==========
        // En mode hors-ligne, on permet la vente (les données seront synchronisées plus tard)
        try {
            const result = await rpc("/web/dataset/call_kw/pos.order/check_stock_levels", {
                model: "pos.order",
                method: "check_stock_levels",
                args: [product_ids, hasDiscount],
                kwargs: {},
            });
            
            console.log("Résultat vérification:", result);
            
            if (result.error) {
                if (result.access_required) {
                    const codeInput = await this._showPasswordPrompt(result.message, discountedProducts);
                    // Log différé : order.name (serveur) n'est disponible qu'après paiement
                    const { success: stockOk, managerId: stockMgrId } = await validateManagerCode(
                        codeInput, hasDiscount ? "discount" : "stock", this,
                        "", result.code_acces || null, null, false
                    );
                    if (!stockOk) {
                        this.dialog.add(AlertDialog, {
                            title: _t("Code incorrect"),
                            body: _t("Le code saisi est invalide. La vente est annulée."),
                        });
                        return;
                    }
                    if (!currentOrder._pendingLogs) currentOrder._pendingLogs = [];
                    const stockPriceInfo = result.rupture_details?.length ? result.rupture_details : null;
                    currentOrder._pendingLogs.push({ manager_id: stockMgrId, action: hasDiscount ? "discount" : "stock", price_info: stockPriceInfo });
                } else {
                    // Blocage définitif : pas d'override possible.
                    this.dialog.add(AlertDialog, {
                        title: _t("Stock indisponible"),
                        body: _t(result.message),
                    });
                    return;
                }
            }
        } catch (error) {
            // Mode hors-ligne détecté - effectuer la vérification localement
            console.warn("Mode hors-ligne détecté - vérification stock locale:", error.message || error);
            
            // ========== Vérification stock LOCALE (mode hors-ligne) ==========
            // Utiliser les données produits en cache pour vérifier le stock
            const produitsRupture = [];
            
            for (const line of orderLines) {
                if (!line || !line.product_id) continue;
                if (line.is_reward_line) continue;
                if (line.price_unit !== undefined && line.price_unit < 0) continue;
                
                const product = line.product_id;
                // Vérifier qty_available dans les données locales du produit
                const qtyAvailable = product.qty_available ?? 0;
                if (qtyAvailable <= 0) {
                    const code = product.default_code || product.barcode || '';
                    const displayName = code ? `[${code}] ${product.name}` : product.name;
                    produitsRupture.push(displayName);
                }
            }
            
            const accessCode = this.config.code_acces;
            
            // Si rupture de stock ET remise
            if (produitsRupture.length > 0 && hasDiscount) {
                const message = "⚠️ Autorisation requise (mode hors-ligne) :\n\n" +
                    "Produits en rupture de stock :\n" +
                    produitsRupture.map(p => `   • ${p}`).join('\n');
                const codeInput = await this._showPasswordPrompt(message, discountedProducts);
                const { success: ok1 } = await validateManagerCode(codeInput, "stock", this, currentOrder?.name || "", accessCode);
                if (!ok1) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Code incorrect"),
                        body: _t("Le code saisi est invalide. La vente est annulée."),
                    });
                    return;
                }
            }
            // Si seulement rupture de stock
            else if (produitsRupture.length > 0) {
                const message = "Les produits suivants sont en rupture de stock :\n" +
                    produitsRupture.map(p => `   • ${p}`).join('\n');
                const codeInput = await this._showPasswordPrompt(message, []);
                const { success: ok2 } = await validateManagerCode(codeInput, "stock", this, currentOrder?.name || "", accessCode);
                if (!ok2) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Code incorrect"),
                        body: _t("Le code saisi est invalide. La vente est annulée."),
                    });
                    return;
                }
            }
            // Si seulement remise
            else if (hasDiscount) {
                const message = "⚠️ Cette commande contient des remises.\nUn code d'accès est requis pour continuer.";
                const codeInput = await this._showPasswordPrompt(message, discountedProducts);
                const { success: ok3 } = await validateManagerCode(codeInput, "discount", this, currentOrder?.name || "", accessCode);
                if (!ok3) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Code incorrect"),
                        body: _t("Le code saisi est invalide. La vente est annulée."),
                    });
                    return;
                }
            }
            // Tout est OK - pas de rupture ni remise
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

            // Bloque l'interception du scanner par le POS global + gère Enter/Escape
            input.addEventListener("keydown", (e) => {
                e.stopPropagation();
                if (e.key === "Enter") okBtn.click();
                else if (e.key === "Escape") cancelBtn.click();
            });
            input.addEventListener("keyup", (e) => e.stopPropagation());

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