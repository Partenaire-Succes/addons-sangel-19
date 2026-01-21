/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

console.warn("🔴 ticket_screen_refund_patch.js LOADED - Patching TicketScreen for refund authorization");

patch(TicketScreen.prototype, {
    
    /**
     * Override onDoRefund to add access code verification for group_pos_user
     */
    async onDoRefund() {
        console.log("🔄 onDoRefund called - checking refund authorization");
        
        const order = this.getSelectedOrder();
        if (!order) {
            console.log("❌ No order selected");
            return;
        }
        
        // Calculate refund amount for information
        let refundAmount = 0;
        const selectedOrderlineId = this.getSelectedOrderlineId();
        if (selectedOrderlineId) {
            const orderline = order.lines.find((line) => line.id == selectedOrderlineId);
            if (orderline) {
                const toRefundDetail = this.getToRefundDetail(orderline);
                if (toRefundDetail && toRefundDetail.qty > 0) {
                    refundAmount = toRefundDetail.qty * orderline.price_unit;
                }
            }
        }
        
        // Check if user needs authorization for refund
        try {
            const result = await rpc("/web/dataset/call_kw/pos.order/check_refund_authorization", {
                model: "pos.order",
                method: "check_refund_authorization",
                args: [refundAmount],
                kwargs: {},
            });
            
            console.log("📋 Refund authorization result:", result);
            
            if (result.error && result.access_required) {
                if (result.code_acces) {
                    // Show password prompt
                    const codeInput = await this._showRefundPasswordPrompt(result.message);
                    
                    if (codeInput === null) {
                        // User cancelled
                        console.log("❌ User cancelled refund authorization");
                        return;
                    }
                    
                    if (codeInput !== result.code_acces) {
                        this.dialog.add(AlertDialog, {
                            title: _t("Code incorrect"),
                            body: _t("Le code saisi est invalide. Le remboursement est annulé."),
                        });
                        return;
                    }
                    
                    console.log("✅ Refund authorization code accepted");
                } else {
                    // No access code configured
                    this.dialog.add(AlertDialog, {
                        title: _t("Remboursement non autorisé"),
                        body: _t(result.message + "\n\nAucun code d'accès configuré. Contactez votre administrateur."),
                    });
                    return;
                }
            }
        } catch (error) {
            // Offline mode - use local config
            console.warn("⚠️ Offline mode detected for refund authorization:", error.message || error);
            
            const accessCode = this.pos.config.code_acces;
            
            // In offline mode, still require code if configured
            if (accessCode) {
                const message = "⚠️ Autorisation requise pour le remboursement (mode hors-ligne).\n\nUn code d'accès est requis pour effectuer cette opération.";
                const codeInput = await this._showRefundPasswordPrompt(message);
                
                if (codeInput === null) {
                    console.log("❌ User cancelled refund authorization (offline)");
                    return;
                }
                
                if (codeInput !== accessCode) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Code incorrect"),
                        body: _t("Le code saisi est invalide. Le remboursement est annulé."),
                    });
                    return;
                }
                
                console.log("✅ Refund authorization code accepted (offline)");
            }
        }
        
        // Authorization passed, proceed with original refund logic
        console.log("✅ Proceeding with refund");
        return super.onDoRefund(...arguments);
    },
    
    /**
     * Show password prompt popup for refund authorization
     * @param {string} message - Message to display
     * @returns {Promise<string|null>} - The entered code or null if cancelled
     */
    async _showRefundPasswordPrompt(message) {
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
            box.style.minWidth = "320px";
            box.style.maxWidth = "450px";

            const title = document.createElement("h3");
            title.style.color = "#dc3545";
            title.style.marginBottom = "15px";
            title.innerText = "🔐 Code d'accès requis - Remboursement";
            box.appendChild(title);

            const msg = document.createElement("p");
            msg.style.whiteSpace = "pre-wrap";
            msg.style.marginBottom = "15px";
            msg.innerText = message;
            box.appendChild(msg);

            const input = document.createElement("input");
            input.type = "password";
            input.placeholder = "Entrez le code d'accès";
            input.style.width = "100%";
            input.style.padding = "10px";
            input.style.marginBottom = "15px";
            input.style.border = "1px solid #ccc";
            input.style.borderRadius = "4px";
            input.style.fontSize = "16px";
            box.appendChild(input);

            const btnRow = document.createElement("div");
            btnRow.style.display = "flex";
            btnRow.style.justifyContent = "flex-end";
            btnRow.style.gap = "10px";

            const cancelBtn = document.createElement("button");
            cancelBtn.innerText = "Annuler";
            cancelBtn.style.padding = "10px 20px";
            cancelBtn.style.border = "1px solid #ccc";
            cancelBtn.style.borderRadius = "4px";
            cancelBtn.style.background = "#f8f9fa";
            cancelBtn.style.cursor = "pointer";
            cancelBtn.onclick = () => {
                document.body.removeChild(overlay);
                resolve(null);
            };

            const okBtn = document.createElement("button");
            okBtn.innerText = "Valider";
            okBtn.style.padding = "10px 20px";
            okBtn.style.border = "none";
            okBtn.style.borderRadius = "4px";
            okBtn.style.background = "#007bff";
            okBtn.style.color = "#fff";
            okBtn.style.cursor = "pointer";
            okBtn.onclick = () => {
                const value = input.value;
                document.body.removeChild(overlay);
                resolve(value);
            };

            // Handle Enter key
            input.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    okBtn.click();
                } else if (e.key === "Escape") {
                    cancelBtn.click();
                }
            });

            btnRow.appendChild(cancelBtn);
            btnRow.appendChild(okBtn);
            box.appendChild(btnRow);
            overlay.appendChild(box);
            document.body.appendChild(overlay);
            input.focus();
        });
    },
});

console.warn("✅ ticket_screen_refund_patch.js - TicketScreen patched successfully");
