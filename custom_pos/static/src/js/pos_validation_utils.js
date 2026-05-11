/** @odoo-module **/
/**
 * Utilitaire de validation des codes managers POS.
 *
 * Flux :
 *  1. Online  → RPC validate_manager_code → log créé côté serveur → retourne manager_name
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
 * @param {object|null}  priceInfo    - Pour price_reduction : { old_price, new_price, product_name }
 * @returns {Promise<{success: boolean, managerName: string|null}>}
 */
export async function validateManagerCode(code, actionKey, pos, orderRef, fallbackCode, priceInfo = null) {
    if (!code) {
        return { success: false, managerName: null };
    }

    const sessionId = pos?.session?.id || false;
    const cashierName = pos?.user?.name || "";

    // ── 1. Online : RPC avec logging ────────────────────────────────────────
    try {
        const result = await rpc("/web/dataset/call_kw/pos.manager.code/validate_manager_code", {
            model: "pos.manager.code",
            method: "validate_manager_code",
            args: [code, actionKey, sessionId, cashierName, orderRef || ""],
            kwargs: { price_info: priceInfo || false },
        });
        return {
            success: result.success === true,
            managerName: result.manager_name || null,
        };
    } catch (_e) {
        // Réseau indisponible → mode hors-ligne
    }

    // ── 2. Offline : comparaison SHA-256 ────────────────────────────────────
    const managers = pos?.models?.["pos.manager.code"]?.getAll?.() || [];
    if (managers.length > 0) {
        const hash = await _sha256(code);
        if (hash) {
            const matched = managers.find((m) => m.code_hash === hash);
            if (matched) {
                return { success: true, managerName: matched.name + " (hors-ligne)" };
            }
        }
    }

    // ── 3. Fallback : code partagé global ────────────────────────────────────
    if (fallbackCode && code === fallbackCode) {
        return { success: true, managerName: null };
    }

    return { success: false, managerName: null };
}
