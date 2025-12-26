import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { roundPrecision } from "@web/core/utils/numbers";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    
    pointsForPrograms(programs) {
        const result = super.pointsForPrograms(programs);
        
        for (const programId in result) {
            const program = this.models["loyalty.program"].get(parseInt(programId));
            
            if (program && program.program_type === 'loyalty') {
                const customPoints = this._calculateCustomLoyaltyPoints(program);
                
                if (customPoints > 0) {
                    result[programId] = [{ points: customPoints }];
                } else {
                    result[programId] = [];
                }
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