/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    
    async addNewPaymentLine(paymentMethod) {
        // Vérification simple pour les paiements alimentaires
        if (paymentMethod.is_food) {
            const order = this.currentOrder;
            const partner = order.partner_id;
            
            // Vérifications de base côté client
            if (!partner) {
                this.dialog.add(AlertDialog, {
                    title: "Client requis",
                    body: "Sélectionnez un client pour le crédit alimentaire.",
                });
                return;
            }

            // Check if partner has food credit balance (more reliable than checking parent_id.is_food)
            if (!partner.food_credit_balance || partner.food_credit_balance <= 0) {
                this.dialog.add(AlertDialog, {
                    title: "Accès refusé",
                    body: "Ce client n'a pas accès au crédit alimentaire ou son solde est épuisé.",
                });
                return;
            }
        }
        if (paymentMethod.is_limit) {
            const order = this.currentOrder;
            const partner = order.partner_id;
            
            // Vérifications de base côté client
            if (!partner) {
                this.dialog.add(AlertDialog, {
                    title: "Client requis",
                    body: "Sélectionnez un client pour le compte client.",
                });
                return;
            }

            if (!partner?.is_limit) {
                this.dialog.add(AlertDialog, {
                    title: "Accès refusé",
                    body: "Ce client n'a pas accès à la limite crédit.",
                });
                return;
            }
        }
        // if (paymentMethod.is_loyalty) {
        //     const order = this.pos.get_order();
        //     const partner = order.get_partner();
            
        //     // Vérifications de base côté client
        //     if (!partner) {
        //         this.dialog.add(AlertDialog, {
        //             title: "Client requis",
        //             body: "Sélectionnez un client pour la carte de fidelité.",
        //         });
        //         return;
        //     }
        // }
        
        // Continuer normalement - la vérification détaillée se fait côté serveur
        return super.addNewPaymentLine(paymentMethod);
    }
});