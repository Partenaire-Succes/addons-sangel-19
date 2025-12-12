// static/src/js/pos_credit_limit_simple.js

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    
    // Vérification simple de la limite de crédit
    _isPaymentMethodAllowed(paymentMethod) {
        const order = this.pos.get_order();
        const customer = order.get_partner();
        
        // Si pas de client ou pas de is_progress, autoriser
        if (!customer || !paymentMethod.is_progress) {
            return true;
        }
        
        const currentCredit = customer.total_due || 0;
        const creditLimit = customer.credit_limit || 0;
        const orderTotal = order.get_total_with_tax();
        
        // Si pas de limite ou limite non dépassée, autoriser
        if (creditLimit <= 0) {
            return true;
        }
        
        return (currentCredit + orderTotal) <= creditLimit;
    },
    
    // Override simple pour bloquer l'ajout de paiement
    addNewPaymentLine(paymentMethod) {
        if (!this._isPaymentMethodAllowed(paymentMethod)) {
            this.dialog.add(AlertDialog, {
                title: _t("Paiement bloqué"),
                body: _t("limite de crédit dépassée."),
            });
            return;
        }
        
        return super.addNewPaymentLine(paymentMethod);
    },
    
    // Filtrer les méthodes disponibles
    get paymentMethods() {
        const methods = super.paymentMethods;
        return methods.filter(method => this._isPaymentMethodAllowed(method));
    }
});