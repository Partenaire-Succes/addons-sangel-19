import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { roundPrecision } from "@web/core/utils/numbers";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(PosOrder.prototype, {

    getLoyaltyPoints() {
        // Log the raw state before calling super so we can diagnose spent=0 issues
        const cpc = this.uiState?.couponPointChanges || {};
        console.log('[LOYALTY] === getLoyaltyPoints ===');
        console.log('[LOYALTY] uiState.couponPointChanges:', JSON.stringify(cpc));

        const rewardLines = this._get_reward_lines
            ? this._get_reward_lines()
            : (this.lines ? this.lines.filter(l => l.is_reward_line) : []);
        console.log('[LOYALTY] reward lines:', rewardLines.map(l => ({
            product: l.product_id?.display_name,
            is_reward_line: l.is_reward_line,
            points_cost: l.points_cost,
            coupon_id_type: typeof l.coupon_id,
            coupon_id_id: typeof l.coupon_id === 'object' ? l.coupon_id?.id : l.coupon_id,
        })));

        const result = super.getLoyaltyPoints(...arguments);
        if (result && result.length) {
            for (const stat of result) {
                if (stat.program?.program_type === 'loyalty') {
                    console.log('[LOYALTY getLoyaltyPoints] result:', {
                        won: stat.points.won,
                        spent: stat.points.spent,
                        balance: stat.points.balance,
                        total: stat.points.total,
                    });
                }
            }
        } else {
            console.log('[LOYALTY getLoyaltyPoints] result vide:', result);
        }
        return result;
    },

    pointsForPrograms(programs) {
        const result = super.pointsForPrograms(programs);

        // Si le client est exclu des points de fidélité, retourner 0 partout
        const partner = this.get_partner ? this.get_partner() : this.partner_id;
        if (partner && partner.no_loyalty_points) {
            for (const programId in result) {
                const program = this.models["loyalty.program"].get(parseInt(programId));
                if (program && program.program_type === 'loyalty') {
                    result[programId] = [];
                }
            }
            return result;
        }

        for (const programId in result) {
            const program = this.models["loyalty.program"].get(parseInt(programId));

            if (program && program.program_type === 'loyalty') {
                const nativeEntries = result[programId] || [];
                // Native pointsForPrograms never returns negative entries for loyalty programs
                // (deductions are handled in postProcessLoyalty). This filter is defensive.
                const deductionEntries = nativeEntries.filter(e => (e.points || 0) < 0);

                console.log('[LOYALTY pointsForPrograms]', {
                    programId,
                    nativeEntries: JSON.stringify(nativeEntries),
                    deductionEntries: JSON.stringify(deductionEntries),
                });

                const customPoints = this._calculateCustomLoyaltyPoints(program);
                const newEntries = [...deductionEntries];
                if (customPoints > 0) {
                    newEntries.push({ points: customPoints });
                }
                result[programId] = newEntries;
                console.log('[LOYALTY pointsForPrograms] final entries:', JSON.stringify(newEntries));
            }
        }

        return result;
    },
    
    /**
     * Get loyalty family record by its ID
     * @param {number} familyId - The ID of the loyalty family
     * @returns {Object|null} The loyalty family record or null
     */
    _getLoyaltyFamily(familyId) {
        if (!familyId) {
            return null;
        }
        
        // Handle case where familyId is an object with id property (Many2one)
        const id = typeof familyId === 'object' ? familyId.id : familyId;
        
        if (!id) {
            return null;
        }
        
        // Try to get from loaded POS data
        const loyaltyFamilies = this.models["loyalty.family"];
        if (loyaltyFamilies) {
            return loyaltyFamilies.get(id) || null;
        }
        
        return null;
    },
    
    _calculateCustomLoyaltyPoints(program) {
        let totalPoints = 0;
        const orderLines = this.getOrderlines();
        
        // Group totals by loyalty family ID for dynamic calculation
        const totalsByFamily = {};
        
        for (const line of orderLines) {
            if (line.is_reward_line || line.qty <= 0) {
                continue;
            }
            
            const product = line.product_id;
            const lineTotal = line.getPriceWithTax();
            
            // ✅ VÉRIFICATION 1 : Le produit est-il éligible ?
            const isEligibleProduct = product.is_eligible !== false; 
            
            if (!isEligibleProduct) {
                continue;
            }
            
            // VÉRIFICATION 2 : family_loyalty_id est-il défini ?
            let familyLoyaltyId = product.family_loyalty_id;
            
            // Si pas trouvé, chercher dans le template
            if (!familyLoyaltyId && product.product_tmpl_id) {
                const template = this.models["product.template"].get(product.product_tmpl_id.id);
                if (template) {
                    familyLoyaltyId = template.family_loyalty_id;
                }
            }
            
            // Skip if no loyalty family assigned
            if (!familyLoyaltyId) {
                continue;
            }
            
            // Get the actual family ID (handle Many2one format)
            const familyId = typeof familyLoyaltyId === 'object' ? familyLoyaltyId.id : familyLoyaltyId;
            
            if (!familyId) {
                continue;
            }
            
            // VÉRIFICATION 3 : Le produit est-il éligible au programme de fidélité ?
            let isEligibleForProgram = false;
            for (const rule of program.rule_ids) {
                if (rule.any_product || rule.validProductIds.has(product.id)) {
                    isEligibleForProgram = true;
                    break;
                }
            }
            
            if (!isEligibleForProgram) {
                continue;
            }
            
            // Accumulate total by family ID
            if (!totalsByFamily[familyId]) {
                totalsByFamily[familyId] = 0;
            }
            totalsByFamily[familyId] += lineTotal;
        }
        
        // Calculate points for each family using dynamic values
        for (const familyId in totalsByFamily) {
            const family = this._getLoyaltyFamily(parseInt(familyId));
            
            if (family && family.price_threshold > 0) {
                // Dynamic calculation: floor(total / price_threshold) * points_earned
                const points = Math.floor(totalsByFamily[familyId] / family.price_threshold) * family.points_earned;
                totalPoints += points;
                console.log(`Family "${family.name}": ${totalsByFamily[familyId]} FCFA -> ${points} points (${family.points_earned} pts / ${family.price_threshold} F)`);
            }
        }
        
        console.log('TOTAL POINTS:', totalPoints);

        return roundPrecision(totalPoints, 0.01);
    }

});

patch(OrderPaymentValidation.prototype, {
    async postProcessLoyalty(order) {
        console.log('[LOYALTY postProcess] === Début postProcessLoyalty ===');

        const cpc = order.uiState?.couponPointChanges || {};
        console.log('[LOYALTY postProcess] couponPointChanges:', JSON.stringify(cpc));

        const rewardLines = order._get_reward_lines ? order._get_reward_lines() : [];
        console.log('[LOYALTY postProcess] reward lines:', rewardLines.map(l => ({
            product: l.product_id?.display_name,
            is_reward_line: l.is_reward_line,
            points_cost: l.points_cost,
            coupon_id_type: typeof l.coupon_id,
            coupon_id_id: typeof l.coupon_id === 'object' ? l.coupon_id?.id : l.coupon_id,
            reward_id: l.reward_id?.id,
        })));

        // 1. Capture amount paid via is_loyalty payment method (e.g. "Carte de fidélité").
        //    This is NOT tracked by getLoyaltyPoints (it's a payment, not a reward line).
        //    We store it on the order so the receipt template can read it as a plain property.
        try {
            // En Odoo 19, les lignes de paiement sont dans order.payment_ids (pas order.paymentlines)
            const paymentlines = order.payment_ids || [];
            const loyaltyPaymentAmt = Math.floor(
                paymentlines
                    .filter(p => p.payment_method_id?.is_loyalty)
                    .reduce((acc, p) => acc + Math.abs(p.amount || 0), 0)
            );
            order.initial_loyalty_payment = loyaltyPaymentAmt;
            console.log('[LOYALTY postProcess] loyaltyPaymentAmt:', loyaltyPaymentAmt);
        } catch (e) {
            console.error('[LOYALTY postProcess] Erreur capture payment:', e);
        }

        // 2. Capture loyalty stats NOW — before super() clears couponPointChanges and reward lines.
        //    This is the only guaranteed moment where spent/won are intact.
        try {
            const stats = order.getLoyaltyPoints?.() || [];
            const stat = stats.find(s => s.program?.program_type === 'loyalty');
            if (stat) {
                if (order.initial_loyalty_balance === null || order.initial_loyalty_balance === undefined) {
                    order.initial_loyalty_balance = stat.points.balance;
                }
                // Always overwrite spent/won here — most reliable capture point.
                order.initial_loyalty_spent = stat.points.spent ?? 0;
                order.initial_loyalty_won   = stat.points.won   ?? 0;
                console.log('[LOYALTY postProcess] Captured → balance:', order.initial_loyalty_balance,
                    '| won:', order.initial_loyalty_won, '| spent:', order.initial_loyalty_spent);
            } else {
                console.log('[LOYALTY postProcess] Aucune stat fidélité trouvée avant super()');
            }
        } catch (e) {
            console.error('[LOYALTY postProcess] Erreur capture stats:', e);
        }

        let result;
        try {
            result = await super.postProcessLoyalty(...arguments);
            console.log('[LOYALTY postProcess] Terminé avec succès');
        } catch (e) {
            console.error('[LOYALTY postProcess] ERREUR:', e);
            throw e;
        }
        return result;
    },
});