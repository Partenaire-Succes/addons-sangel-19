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

        // ========== Vérification réduction de prix ==========
        // Collecter les lignes avec prix modifié (pour vérification backend)
        const priceReductionLines = [];
        orderLines.forEach(line => {
            if (!line || !line.product_id) return;
            if (line.is_reward_line) return;
            if (line.price_unit !== undefined && line.price_unit < 0) return;
            
            const product = line.product_id;
            const originalPrice = product.lst_price;
            const currentPrice = line.price_unit;
            
            // Vérifier si le prix a été réduit
            if (currentPrice < originalPrice) {
                priceReductionLines.push({
                    product_id: product.id,
                    unit_price: currentPrice,
                    product_name: product.display_name,
                    original_price: originalPrice,
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
                    if (priceResult.code_acces) {
                        const priceCodeInput = await this._showPasswordPrompt(priceResult.message, []);
                        if (priceCodeInput !== priceResult.code_acces) {
                            this.dialog.add(AlertDialog, {
                                title: _t("Code incorrect"),
                                body: _t("Le code saisi est invalide. La vente est annulée."),
                            });
                            return;
                        }
                    } else {
                        this.dialog.add(AlertDialog, {
                            title: _t("Réduction de prix non autorisée"),
                            body: _t(priceResult.message + "\n\nAucun code d'accès configuré."),
                        });
                        return;
                    }
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
                        if (codeInput !== accessCode) {
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
                
                if (accessCode) {
                    const codeInput = await this._showPasswordPrompt(message, discountedProducts);
                    if (codeInput !== accessCode) {
                        this.dialog.add(AlertDialog, {
                            title: _t("Code incorrect"),
                            body: _t("Le code saisi est invalide. La vente est annulée."),
                        });
                        return;
                    }
                } else {
                    this.dialog.add(AlertDialog, {
                        title: _t("Stock indisponible"),
                        body: _t(message + "\n\nAucun code d'accès configuré."),
                    });
                    return;
                }
            }
            // Si seulement rupture de stock
            else if (produitsRupture.length > 0) {
                const message = "Les produits suivants sont en rupture de stock :\n" +
                    produitsRupture.map(p => `   • ${p}`).join('\n');
                
                if (accessCode) {
                    const codeInput = await this._showPasswordPrompt(message, []);
                    if (codeInput !== accessCode) {
                        this.dialog.add(AlertDialog, {
                            title: _t("Code incorrect"),
                            body: _t("Le code saisi est invalide. La vente est annulée."),
                        });
                        return;
                    }
                } else {
                    this.dialog.add(AlertDialog, {
                        title: _t("Stock indisponible"),
                        body: _t(message + "\n\nAucun code d'accès configuré."),
                    });
                    return;
                }
            }
            // Si seulement remise
            else if (hasDiscount) {
                const message = "⚠️ Cette commande contient des remises.\nUn code d'accès est requis pour continuer.";
                
                if (accessCode) {
                    const codeInput = await this._showPasswordPrompt(message, discountedProducts);
                    if (codeInput !== accessCode) {
                        this.dialog.add(AlertDialog, {
                            title: _t("Code incorrect"),
                            body: _t("Le code saisi est invalide. La vente est annulée."),
                        });
                        return;
                    }
                } else {
                    console.warn("Mode hors-ligne: Pas de code d'accès configuré - vente autorisée sans vérification");
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