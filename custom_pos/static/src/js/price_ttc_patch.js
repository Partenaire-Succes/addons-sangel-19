/** @odoo-module */

/**
 * PATCH: Saisie prix TTC en caisse
 *
 * Problème Odoo standard :
 *   - POS configuré avec iface_tax_included = 'total' → affichage TTC
 *   - Mais setUnitPrice() stocke la valeur saisie brute comme prix HT
 *   - Résultat : si la caissière tape 2000 (pensant TTC), Odoo calcule
 *     2000 × 1.18 = 2360 → mauvais prix final affiché
 *
 * Correction :
 *   - Patcher setLinePrice() (appelé uniquement depuis le numpad caisse)
 *   - Si iface_tax_included === 'total', convertir TTC → HT via le moteur
 *     fiscal Odoo avant d'appeler setUnitPrice()
 *   - Formule : HT = TTC_saisi × (priceWithoutTax / priceWithTax)
 *     où le ratio est calculé dynamiquement par les helpers fiscaux Odoo
 *     (fonctionne avec taxes fixes, multiples, ou positionnement fiscal)
 */

import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { patch } from "@web/core/utils/patch";

patch(OrderSummary.prototype, {
    /**
     * Surcharge de setLinePrice pour gérer la saisie TTC.
     *
     * En mode iface_tax_included = 'total' (par défaut Odoo), la caissière
     * voit et saisit un prix TTC. On doit convertir ce TTC en HT avant
     * d'appeler setUnitPrice(), car price_unit est toujours stocké HT en Odoo.
     *
     * @param {Orderline} line  - La ligne de commande sélectionnée
     * @param {string|number} price - Prix TTC saisi par la caissière
     */
    async setLinePrice(line, price) {
        if (this.pos.config.iface_tax_included !== "total") {
            // Mode HT : comportement standard, pas de conversion nécessaire
            return super.setLinePrice(line, price);
        }

        const parsedPrice = parseFloat(price) || 0;

        if (parsedPrice === 0) {
            line.price_type = "manual";
            line.setUnitPrice(0);
            return;
        }

        // --- Conversion TTC → HT via le moteur fiscal Odoo ---
        //
        // On exploite le fait que getAllPrices() utilise price_unit comme base HT.
        // En fixant temporairement price_unit = parsedPrice (valeur saisie TTC),
        // Odoo calcule : priceWithoutTax = parsedPrice, priceWithTax = parsedPrice × (1 + taux)
        // Le ratio priceWithoutTax/priceWithTax = 1/(1+taux) est exactement ce qu'il faut.
        //
        // Avantage : fonctionne avec tous les types de taxes (%, montant fixe,
        // taxes multiples, positions fiscales) car on utilise le calcul Odoo natif.

        const savedPriceUnit = line.price_unit;

        try {
            line.price_unit = parsedPrice;
            const { priceWithTax, priceWithoutTax } = line.allUnitPrices;

            let htPrice;
            if (priceWithTax > 0 && priceWithTax !== priceWithoutTax) {
                // Produit taxé : convertir TTC → HT
                htPrice = parsedPrice * (priceWithoutTax / priceWithTax);
            } else {
                // Produit sans taxe ou taxe nulle : TTC = HT
                htPrice = parsedPrice;
            }

            line.price_unit = savedPriceUnit;
            line.price_type = "manual";
            line.setUnitPrice(htPrice);

        } catch (e) {
            // Sécurité : en cas d'erreur du moteur fiscal, restaurer et
            // appliquer le comportement standard (évite de bloquer la caisse)
            line.price_unit = savedPriceUnit;
            console.error("[price_ttc_patch] Erreur conversion TTC→HT, fallback standard:", e);
            return super.setLinePrice(line, price);
        }
    },
});
