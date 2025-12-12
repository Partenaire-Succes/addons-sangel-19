import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";
import { roundPrecision } from "@web/core/utils/numbers";

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
    
    _calculateCustomLoyaltyPoints(program) {
        let totalPoints = 0;
        const orderLines = this.getOrderlines();
        
        const pointsFamily200 = {};
        const pointsFamily1000 = {};
        
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
            
            // VÉRIFICATION 2 : family_loyalty est-il défini ?
            let familyLoyalty = product.family_loyalty;
            
            // Si pas trouvé, chercher dans le template
            if (!familyLoyalty && product.product_tmpl_id) {
                const template = this.models["product.template"].get(product.product_tmpl_id.id);
                if (template) {
                    familyLoyalty = template.family_loyalty;
                }
            }
            
            if (familyLoyalty === undefined || familyLoyalty === null || 
                familyLoyalty === false || familyLoyalty === '') {
                continue;
            }
            
            familyLoyalty = String(familyLoyalty);
            
            if (familyLoyalty === 'none' || familyLoyalty === 'false') {
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
            
            // CALCUL DES POINTS
            if (familyLoyalty === '200') {
                if (!pointsFamily200[product.id]) {
                    pointsFamily200[product.id] = 0;
                }
                pointsFamily200[product.id] += lineTotal;
            } else if (familyLoyalty === '1000') {
                if (!pointsFamily1000[product.id]) {
                    pointsFamily1000[product.id] = 0;
                }
                pointsFamily1000[product.id] += lineTotal;
            }
        }
        
        for (const productId in pointsFamily200) {
            const points = Math.floor(pointsFamily200[productId] / 200);
            totalPoints += points;
        }
        
        for (const productId in pointsFamily1000) {
            const points = Math.floor(pointsFamily1000[productId] / 1000);
            totalPoints += points;
        }
        
        console.log('TOTAL POINTS:', totalPoints);
        
        return roundPrecision(totalPoints, 0.01);
    }
    
});