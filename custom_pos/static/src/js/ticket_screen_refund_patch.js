/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { InvoiceButton } from "@point_of_sale/app/screens/ticket_screen/invoice_button/invoice_button";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { validateManagerCode } from "@custom_pos/js/pos_validation_utils";

// ============================================================
// HELPER MODULE — Popup code d'accès (partagé par tous les patches)
// ============================================================

/**
 * Affiche une popup code d'accès native DOM (sans dépendance OWL).
 * @param {string} actionLabel  — libellé de l'action demandée
 * @returns {Promise<string|null>}  — code saisi, ou null si annulation
 */
function _showCodePromptDialog(actionLabel) {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;";

        const box = document.createElement("div");
        box.style.cssText = "background:#fff;padding:24px;border-radius:8px;box-shadow:0 0 15px rgba(0,0,0,0.3);min-width:340px;max-width:460px;";

        const title = document.createElement("h3");
        title.style.cssText = "color:#e67e22;margin-bottom:12px;font-size:16px;";
        title.innerText = "🔐 Code d'accès requis";
        box.appendChild(title);

        const msg = document.createElement("p");
        msg.style.cssText = "margin-bottom:14px;color:#555;font-size:14px;white-space:pre-wrap;";
        msg.innerText = `Action : ${actionLabel}\nUn code d'accès superviseur est requis.`;
        box.appendChild(msg);

        const input = document.createElement("input");
        input.type = "password";
        input.placeholder = "Entrez le code d'accès";
        input.style.cssText = "width:100%;padding:10px;margin-bottom:14px;border:1px solid #ccc;border-radius:4px;font-size:15px;box-sizing:border-box;";
        box.appendChild(input);

        const btnRow = document.createElement("div");
        btnRow.style.cssText = "display:flex;justify-content:flex-end;gap:10px;";

        const cancelBtn = document.createElement("button");
        cancelBtn.innerText = "Annuler";
        cancelBtn.style.cssText = "padding:9px 20px;border:1px solid #ccc;border-radius:4px;background:#f8f9fa;cursor:pointer;font-size:14px;";
        cancelBtn.onclick = () => { document.body.removeChild(overlay); resolve(null); };

        const okBtn = document.createElement("button");
        okBtn.innerText = "Valider";
        okBtn.style.cssText = "padding:9px 20px;border:none;border-radius:4px;background:#e67e22;color:#fff;cursor:pointer;font-size:14px;";
        okBtn.onclick = () => { document.body.removeChild(overlay); resolve(input.value); };

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
}

/**
 * Vérifie si la caissière est autorisée à effectuer une action.
 * Utilise validateManagerCode pour logging + codes individuels par manager.
 *
 * @param {boolean} isCaissiere  — this.pos.user._is_caissiere
 * @param {string}  code_acces   — this.pos.config.code_acces (fallback global)
 * @param {object}  dialog       — service dialog (this.dialog)
 * @param {string}  actionLabel  — libellé affiché dans la popup
 * @param {object}  pos          — instance PosStore (this.pos)
 * @param {string}  actionKey    — clé stable pour le log ('print'|'details'|'invoice'|...)
 * @param {string}  orderRef     — référence commande (optionnel)
 * @returns {Promise<boolean>}
 */
async function _checkCaissiereCodeAccess(isCaissiere, code_acces, dialog, actionLabel, pos, actionKey, orderRef) {
    if (!isCaissiere) return true;

    const input = await _showCodePromptDialog(actionLabel);
    if (input === null) return false;

    const { success } = await validateManagerCode(
        input, actionKey, pos, orderRef || '', code_acces
    );

    if (!success) {
        dialog.add(AlertDialog, {
            title: _t("Code incorrect"),
            body: _t("Le code saisi est invalide. Action annulée."),
        });
        return false;
    }
    return true;
}

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
                    
                    const orderRef = order?.name || "";
                    const { success: codeOk } = await validateManagerCode(
                        codeInput, "refund", this.pos, orderRef, result.code_acces
                    );
                    if (!codeOk) {
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
                
                const { success: offlineOk } = await validateManagerCode(
                    codeInput, "refund", this.pos, order?.name || "", accessCode
                );
                if (!offlineOk) {
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

            // Bloque l'interception du scanner par le POS global + gère Enter/Escape
            input.addEventListener("keydown", (e) => {
                e.stopPropagation();
                if (e.key === "Enter") {
                    okBtn.click();
                } else if (e.key === "Escape") {
                    cancelBtn.click();
                }
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
});

console.warn("✅ ticket_screen_refund_patch.js - TicketScreen patched successfully");

// ============================================================
// PATCH 2 : TicketScreen — Verrouillage "Imprimer le ticket" + "Détails"
// ============================================================
patch(TicketScreen.prototype, {

    /**
     * Patch : Imprimer le ticket — verrouillé pour les caissières
     * (doPrint wrapping this.print → patch ici intercepte bien avant l'impression)
     */
    async print(order) {
        const ok = await _checkCaissiereCodeAccess(
            this.pos.user._is_caissiere,
            this.pos.config.code_acces,
            this.dialog,
            _t("Imprimer le ticket"),
            this.pos,
            "print",
            order?.name || ""
        );
        if (!ok) return;
        return super.print(...arguments);
    },

    /**
     * Nouvelle méthode : Détails — appelée depuis le patch XML
     * Verrouillée pour les caissières avant d'ouvrir les détails
     */
    async onClickDetails(order) {
        const ok = await _checkCaissiereCodeAccess(
            this.pos.user._is_caissiere,
            this.pos.config.code_acces,
            this.dialog,
            _t("Détails commande"),
            this.pos,
            "details",
            order?.name || ""
        );
        if (!ok) return;
        this.pos.orderDetails(order);
    },
});

// ============================================================
// PATCH 3 : InvoiceButton — Verrouillage "Facture"
// POURQUOI ICI et non dans onInvoiceOrder de TicketScreen ?
// → onInvoiceOrder (TicketScreen) est un CALLBACK appelé APRÈS que la facture
//   est déjà créée côté serveur. Intercepter ici (_invoiceOrder) bloque
//   AVANT toute création de facture, au tout début du traitement.
// ============================================================
patch(InvoiceButton.prototype, {

    async _invoiceOrder() {
        const orderRef = this.props?.order?.name || this.pos?.selectedOrder?.name || "";
        const ok = await _checkCaissiereCodeAccess(
            this.pos.user._is_caissiere,
            this.pos.config.code_acces,
            this.dialog,
            _t("Facture"),
            this.pos,
            "invoice",
            orderRef
        );
        if (!ok) return;
        return super._invoiceOrder(...arguments);
    },
});

console.warn("✅ ticket_screen_refund_patch.js - Patch 2 (Détails/Impression) + Patch 3 (InvoiceButton) appliqués");
