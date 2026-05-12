/** @odoo-module **/
/**
 * Utilitaire de validation des codes managers POS.
 *
 * Flux :
 *  1. Online  → RPC validate_manager_code → log créé côté serveur → retourne manager_name + manager_id
 *  2. Offline → SHA-256 comparé aux hashes chargés au démarrage POS
 *  3. Fallback final → code partagé pos.config.code_acces (rétrocompatibilité)
 *
 * Le code en clair ne transite JAMAIS vers le navigateur.
 */
import { rpc } from "@web/core/network/rpc";

/**
 * SHA-256 d'une chaîne (Web Crypto API).
 * Retourne null si crypto.subtle non disponible (contexte non-HTTPS).
 */
async function _sha256(str) {
    try {
        const buf = await crypto.subtle.digest(
            "SHA-256",
            new TextEncoder().encode(str)
        );
        return Array.from(new Uint8Array(buf))
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("");
    } catch (_e) {
        return null;
    }
}

/**
 * Valide un code manager via RPC (online) ou SHA-256 (offline).
 *
 * @param {string}       code         - Code saisi ou scanné par le manager
 * @param {string}       actionKey    - 'refund'|'discount'|'stock'|'price_reduction'|'print'|'details'|'invoice'
 * @param {object}       pos          - Instance PosStore
 * @param {string}       orderRef     - Référence commande (optionnel)
 * @param {string}       fallbackCode - Code partagé global (pos.config.code_acces)
 * @param {object|null}  priceInfo    - Pour price_reduction : liste de {produit, avant, apres}
 * @param {boolean}      createLog    - Si false, valide sans créer de log (log différé)
 * @returns {Promise<{success: boolean, managerName: string|null, managerId: number|null}>}
 */
export async function validateManagerCode(code, actionKey, pos, orderRef, fallbackCode, priceInfo = null, createLog = true) {
    if (!code) {
        return { success: false, managerName: null, managerId: null };
    }

    const sessionId = pos?.session?.id || false;
    const cashierName = pos?.user?.name || "";

    // ── 1. Online : RPC avec logging optionnel ──────────────────────────────
    try {
        const result = await rpc("/web/dataset/call_kw/pos.manager.code/validate_manager_code", {
            model: "pos.manager.code",
            method: "validate_manager_code",
            args: [code, actionKey, sessionId, cashierName, orderRef || ""],
            kwargs: { price_info: priceInfo || false, create_log: createLog },
        });
        return {
            success: result.success === true,
            managerName: result.manager_name || null,
            managerId: result.manager_id || null,
        };
    } catch (_e) {
        // Réseau indisponible ou droits insuffisants → mode hors-ligne
        console.warn("[validateManagerCode] RPC échoué :", _e?.message || _e);
    }

    // ── 2. Offline : comparaison SHA-256 ────────────────────────────────────
    const managers = pos?.models?.["pos.manager.code"]?.getAll?.() || [];
    if (managers.length > 0) {
        const hash = await _sha256(code);
        if (hash) {
            const matched = managers.find((m) => m.code_hash === hash);
            if (matched) {
                return { success: true, managerName: matched.name + " (hors-ligne)", managerId: matched.id || null };
            }
        }
    }

    // ── 3. Fallback : code partagé global ────────────────────────────────────
    if (fallbackCode && code === fallbackCode) {
        return { success: true, managerName: null, managerId: null };
    }

    return { success: false, managerName: null, managerId: null };
}

/**
 * Crée les logs différés après finalisation du ticket (order_ref connu).
 * Appelé depuis le patch PaymentScreen après validation du paiement.
 *
 * @param {Array}   pendingLogs  - [{manager_id, action, price_info}]
 * @param {object}  pos          - Instance PosStore
 * @param {string}  orderRef     - Référence finale du ticket
 */
export async function createDeferredLogs(pendingLogs, pos, orderRef) {
    if (!pendingLogs?.length) return;
    const sessionId = pos?.session?.id || false;
    const cashierName = pos?.user?.name || "";
    try {
        await rpc("/web/dataset/call_kw/pos.manager.code/create_deferred_logs", {
            model: "pos.manager.code",
            method: "create_deferred_logs",
            args: [pendingLogs, sessionId, cashierName, orderRef || ""],
            kwargs: {},
        });
    } catch (_e) {
        console.warn("[createDeferredLogs] RPC échoué :", _e?.message || _e);
    }
}
