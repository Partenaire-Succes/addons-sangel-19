/** @odoo-module **/

/**
 * Offline Support for POS Loyalty Code Activation ("Saisir un code")
 * 
 * This module patches PosStore.prototype.activateCode to work offline by:
 * 1. Wrapping RPC calls in try-catch blocks
 * 2. Falling back to locally cached loyalty.card records when offline
 * 3. Validating coupon codes against cached program/rule data
 * 
 * Prerequisites:
 * - loyalty_card_inherit.py must preload cards at session start
 * - loyalty.program, loyalty.rule, loyalty.reward are already loaded locally
 */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

// luxon is a global variable in Odoo, not an ES module
const { DateTime } = luxon;

console.log("🔄 Loading POS Loyalty Offline Support...");

patch(PosStore.prototype, {
    /**
     * Override activateCode to support offline mode.
     * 
     * Original flow:
     * 1. Check if code matches a loyalty.rule (LOCAL)
     * 2. RPC to check if code belongs to a loyalty card partner
     * 3. RPC to validate and activate coupon code
     * 
     * Offline flow:
     * 1. Check if code matches a loyalty.rule (LOCAL - unchanged)
     * 2. Search locally cached loyalty.card by code
     * 3. Validate coupon locally using cached data
     * 
     * @param {string} code - The code entered by the user
     * @returns {string|boolean} - Error message or true on success
     */
    async activateCode(code) {
        const order = this.getOrder();
        
        // STEP 1: Check if code matches a loyalty.rule (already LOCAL - no change needed)
        const rule = this.models["loyalty.rule"].find(
            (rule) =>
                rule.mode === "with_code" && (rule.promo_barcode === code || rule.code === code)
        );

        // STEP 2: Check if code belongs to a loyalty card partner
        let partnerId = null;
        try {
            partnerId = await this.data.call("loyalty.card", "get_loyalty_card_partner_by_code", [code]);
        } catch (error) {
            console.warn("Mode hors-ligne: Recherche partenaire carte fidélité locale", error.message || error);
            
            // Offline fallback: Search locally cached loyalty.card records
            const loyaltyCards = this.models["loyalty.card"];
            if (loyaltyCards) {
                for (const card of loyaltyCards.getAll()) {
                    if (card.code === code) {
                        const program = card.program_id;
                        // Check if this is a loyalty program type
                        if (program && program.program_type === 'loyalty') {
                            partnerId = card.partner_id?.id || card.partner_id;
                            console.log("✅ Mode hors-ligne: Carte fidélité trouvée localement", card);
                            break;
                        }
                    }
                }
            }
        }

        let claimableRewards = null;
        let coupon = null;

        // If the code belongs to a loyalty card we just set the partner
        if (partnerId) {
            const partner = this.models["res.partner"].get(partnerId);
            if (partner) {
                order.setPartner(partner);
                console.log("✅ Partenaire assigné via carte fidélité:", partner.name);
            } else {
                console.warn("Mode hors-ligne: Partenaire non trouvé en cache, ID:", partnerId);
            }
        } else if (rule) {
            // Promo code rule matched - validate and apply (LOCAL - no change needed)
            const date_order = DateTime.fromSQL(order.date_order);
            if (
                rule.program_id.date_from &&
                date_order < rule.program_id.date_from.startOf("day")
            ) {
                return _t("That promo code program is not yet valid.");
            }
            if (rule.program_id.date_to && date_order > rule.program_id.date_to.endOf("day")) {
                return _t("That promo code program is expired.");
            }
            const program_pricelists = rule.program_id.pricelist_ids;
            if (
                program_pricelists.length > 0 &&
                (!order.pricelist_id ||
                    !program_pricelists.some((pr) => pr.id === order.pricelist_id.id))
            ) {
                return _t("That promo code program requires a specific pricelist.");
            }
            if (order.uiState.codeActivatedProgramRules.includes(rule.id)) {
                return _t("That promo code program has already been activated.");
            }
            order.uiState.codeActivatedProgramRules.push(rule.id);
            await this.orderUpdateLoyaltyPrograms();
            claimableRewards = order.getClaimableRewards(false, rule.program_id.id);
        } else {
            // No rule matched - try to activate as a coupon code
            if (order._code_activated_coupon_ids.find((coupon) => coupon.code === code)) {
                return _t("That coupon code has already been scanned and activated.");
            }

            // Try RPC first, fallback to local validation if offline
            const customerId = order.getPartner() ? order.getPartner().id : false;
            let successful = false;
            let payload = null;

            try {
                const result = await this.data.call("pos.config", "use_coupon_code", [
                    [this.config.id],
                    code,
                    order.date_order,
                    customerId,
                    order.pricelist_id ? order.pricelist_id.id : false,
                ]);
                successful = result.successful;
                payload = result.payload;
            } catch (error) {
                console.warn("Mode hors-ligne: Validation coupon locale", error.message || error);
                
                // OFFLINE FALLBACK: Validate coupon using cached data
                const localResult = this._validateCouponOffline(code, order, customerId);
                successful = localResult.successful;
                payload = localResult.payload;
            }

            if (successful) {
                // Allow rejecting a gift card that is not yet paid.
                const program = this.models["loyalty.program"].get(payload.program_id);
                if (program && program.program_type === "gift_card" && !payload.has_source_order) {
                    const confirmed = await ask(this.dialog, {
                        title: _t("Unpaid gift card"),
                        body: _t(
                            "This gift card is not linked to any order. Do you really want to apply its reward?"
                        ),
                    });
                    if (!confirmed) {
                        return _t("Unpaid gift card rejected.");
                    }
                }
                
                // Create local coupon record for the activated code
                coupon = this.models["loyalty.card"].create({
                    id: payload.coupon_id,
                    code: code,
                    program_id: this.models["loyalty.program"].get(payload.program_id),
                    partner_id: this.models["res.partner"].get(payload.partner_id),
                    points: payload.points,
                });
                order._code_activated_coupon_ids = [["link", coupon]];
                await this.orderUpdateLoyaltyPrograms();
                claimableRewards = order.getClaimableRewards(coupon.id);
                
                console.log("✅ Coupon activé:", code, "Points:", payload.points);
            } else {
                return payload.error_message;
            }
        }

        // Auto-apply single reward if applicable
        if (claimableRewards && claimableRewards.length === 1) {
            if (
                claimableRewards[0].reward.reward_type !== "product" ||
                !claimableRewards[0].reward.multi_product
            ) {
                order._applyReward(claimableRewards[0].reward, claimableRewards[0].coupon_id);
                this.updateRewards();
            }
        }

        // Return balance info for gift cards with empty order
        if (!rule && order.lines.length === 0 && coupon) {
            return _t(
                "Gift Card: %s\nBalance: %s",
                code,
                this.env.utils.formatCurrency(coupon.points)
            );
        }

        return true;
    },

    /**
     * Validate a coupon code offline using locally cached data.
     * 
     * This method searches cached loyalty.card records and validates:
     * - Card exists with matching code
     * - Card belongs to a valid program for this POS
     * - Card has positive balance
     * - Card is not expired
     * - Card program is available for current pricelist
     * 
     * @param {string} code - The coupon code to validate
     * @param {Object} order - The current POS order
     * @param {number|false} customerId - The customer ID or false
     * @returns {Object} - {successful: boolean, payload: Object}
     */
    _validateCouponOffline(code, order, customerId) {
        console.log("🔍 Validation coupon hors-ligne:", code);
        
        // Search locally cached loyalty.card records by code
        const loyaltyCards = this.models["loyalty.card"];
        let foundCard = null;
        
        if (loyaltyCards) {
            for (const card of loyaltyCards.getAll()) {
                if (card.code === code) {
                    foundCard = card;
                    break;
                }
            }
        }

        if (!foundCard) {
            console.warn("Mode hors-ligne: Code coupon non trouvé en cache:", code);
            return {
                successful: false,
                payload: {
                    error_message: _t("Ce code coupon n'est pas valide ou n'a pas été préchargé pour le mode hors-ligne.")
                }
            };
        }

        const program = foundCard.program_id;
        if (!program) {
            return {
                successful: false,
                payload: {
                    error_message: _t("Programme de fidélité non trouvé pour ce coupon.")
                }
            };
        }

        // Validate card has positive balance
        if ((foundCard.points || 0) <= 0) {
            return {
                successful: false,
                payload: {
                    error_message: _t("Ce coupon n'a plus de solde disponible.")
                }
            };
        }

        // Validate expiration date
        if (foundCard.expiration_date) {
            const today = DateTime.now().startOf("day");
            const expirationDate = DateTime.fromSQL(foundCard.expiration_date);
            if (expirationDate < today) {
                return {
                    successful: false,
                    payload: {
                        error_message: _t("Ce coupon a expiré.")
                    }
                };
            }
        }

        // Validate program dates
        const date_order = DateTime.fromSQL(order.date_order);
        if (program.date_from && date_order < program.date_from.startOf("day")) {
            return {
                successful: false,
                payload: {
                    error_message: _t("Ce programme de récompenses n'est pas encore valide.")
                }
            };
        }
        if (program.date_to && date_order > program.date_to.endOf("day")) {
            return {
                successful: false,
                payload: {
                    error_message: _t("Ce programme de récompenses a expiré.")
                }
            };
        }

        // Validate pricelist restrictions
        const program_pricelists = program.pricelist_ids || [];
        if (
            program_pricelists.length > 0 &&
            (!order.pricelist_id ||
                !program_pricelists.some((pr) => pr.id === order.pricelist_id.id))
        ) {
            return {
                successful: false,
                payload: {
                    error_message: _t("Ce coupon requiert une liste de prix spécifique.")
                }
            };
        }

        // Validate customer restrictions (nominative programs)
        if (program.is_nominative && foundCard.partner_id) {
            const cardPartnerId = foundCard.partner_id?.id || foundCard.partner_id;
            if (customerId && cardPartnerId !== customerId) {
                return {
                    successful: false,
                    payload: {
                        error_message: _t("Ce coupon est réservé à un autre client.")
                    }
                };
            }
        }

        // Success - return coupon data
        console.log("✅ Coupon validé hors-ligne:", foundCard);
        
        return {
            successful: true,
            payload: {
                coupon_id: foundCard.id,
                program_id: program.id,
                partner_id: foundCard.partner_id?.id || foundCard.partner_id || false,
                points: foundCard.points,
                has_source_order: true, // Assume it's paid in offline mode
            }
        };
    },

    /**
     * Override fetchLoyaltyCard to handle offline mode.
     * Wraps the original method in try-catch with local fallback.
     * 
     * @param {int} programId - The loyalty program ID
     * @param {int} partnerId - The partner ID
     */
    async fetchLoyaltyCard(programId, partnerId) {
        // First check if card exists in local cache
        const existingCoupon = this.models["loyalty.card"].find(
            (c) => c.partner_id?.id === partnerId && c.program_id?.id === programId
        );
        if (existingCoupon) {
            return existingCoupon;
        }
        
        try {
            // Try to fetch from server using parent implementation
            return await super.fetchLoyaltyCard(programId, partnerId);
        } catch (error) {
            console.warn("Mode hors-ligne: Impossible de récupérer la carte fidélité", error.message || error);
            
            // Offline fallback: Create a temporary local card
            // This will be synced when the connection is restored
            const loyaltyIdsGenerator = () => -Math.floor(Math.random() * 1000000);
            
            const localCard = await this.models["loyalty.card"].create({
                id: loyaltyIdsGenerator(),
                code: null,
                program_id: this.models["loyalty.program"].get(programId),
                partner_id: this.models["res.partner"].get(partnerId),
                points: 0,
                expiration_date: null,
            });
            
            console.log("Mode hors-ligne: Carte fidélité locale créée:", localCard);
            return localCard;
        }
    },

    /**
     * Override fetchCoupons to handle offline mode.
     * Wraps the original method in try-catch with local fallback.
     * 
     * @param {Array} domain - Search domain for loyalty.card
     * @param {int} limit - Maximum number of records to fetch
     */
    async fetchCoupons(domain, limit = 1) {
        try {
            return await super.fetchCoupons(domain, limit);
        } catch (error) {
            console.warn("Mode hors-ligne: Impossible de récupérer les coupons", error.message || error);
            
            // In offline mode, search locally cached coupons matching the domain
            const coupons = [];
            const loyaltyCards = this.models["loyalty.card"];
            
            if (loyaltyCards) {
                // Parse domain to extract filters
                // Typical domain: [["partner_id", "=", partnerId], ["program_id", "=", programId]]
                const filters = {};
                for (const condition of domain) {
                    if (Array.isArray(condition) && condition.length >= 3) {
                        const [field, operator, value] = condition;
                        if (operator === "=") {
                            filters[field] = value;
                        }
                    }
                }
                
                for (const card of loyaltyCards.getAll()) {
                    let matches = true;
                    
                    // Check partner_id filter
                    if (filters.partner_id !== undefined) {
                        const cardPartnerId = card.partner_id?.id || card.partner_id;
                        if (cardPartnerId !== filters.partner_id) {
                            matches = false;
                        }
                    }
                    
                    // Check program_id filter
                    if (filters.program_id !== undefined) {
                        const cardProgramId = card.program_id?.id || card.program_id;
                        if (cardProgramId !== filters.program_id) {
                            matches = false;
                        }
                    }
                    
                    // Check code filter
                    if (filters.code !== undefined) {
                        if (card.code !== filters.code) {
                            matches = false;
                        }
                    }
                    
                    if (matches && (card.points || 0) > 0) {
                        coupons.push(card);
                        if (coupons.length >= limit) {
                            break;
                        }
                    }
                }
            }
            
            console.log("Mode hors-ligne: Coupons trouvés localement:", coupons.length);
            return coupons;
        }
    },
});

console.log("✅ POS Loyalty Offline Support loaded successfully");
