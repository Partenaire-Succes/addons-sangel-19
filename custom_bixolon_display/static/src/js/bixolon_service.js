/** @odoo-module **/

/**
 * BixolonDisplayManager — communication série avec le Bixolon BCD-2000
 * via Web Serial API (Edge/Chrome 89+).
 *
 * Protocole VFD Bixolon BCD-2000 (2 lignes × 20 caractères, ASCII/CP437) :
 *   0x0C              = Effacer l'écran + curseur en ligne 1, col 1
 *   (pas de séquences ANSI/VT100 — le BCD-2000 les affiche comme du texte
 *    brut ; le passage à la ligne 2 se fait via le retour-ligne automatique
 *    du VFD après 20 caractères)
 *   Baud : 9600, 8 bits, pas de parité, 1 stop bit
 */

// Caractères Unicode fréquents dans les montants formatés par Odoo (espaces
// insécables utilisées comme séparateurs de milliers, symbole de devise,
// guillemets/tirets typographiques…) que le VFD ne sait pas afficher. On les
// convertit en équivalents ASCII *avant* le remplacement générique par '?',
// pour éviter que les prix s'affichent du genre "5?893?F?CFA".
// Couples [code Unicode, remplacement ASCII] — on passe par String.fromCharCode
// pour éviter d'écrire des caractères invisibles en dur dans le code source.
const CHAR_REPLACEMENTS = Object.fromEntries([
    [0x00A0, ' '],     // espace insecable (NBSP)
    [0x202F, ' '],     // espace fine insecable (separateur de milliers fr)
    [0x2009, ' '],     // espace fine
    [0x2007, ' '],     // espace tabulaire
    [0x20AC, 'EUR'],   // symbole euro
    [0x2018, "'"], [0x2019, "'"],   // guillemets simples typographiques
    [0x201C, '"'], [0x201D, '"'],   // guillemets doubles typographiques
    [0x2013, '-'], [0x2014, '-'],   // tirets demi-cadratin / cadratin
    [0x2026, '...'],                 // points de suspension
].map(([code, repl]) => [String.fromCharCode(code), repl]));

class BixolonDisplayManager {
    constructor() {
        this.port        = null;
        this.writer      = null;
        this.isConnected = false;
        this._writing    = false;   // verrou : évite les écritures concurrentes
        this.BAUD_RATE   = 9600;
        this.WIDTH       = 20;
        this.storeName   = 'SANGEL YOP SARL';   // valeur par défaut, écrasée via setStoreName()
    }

    /**
     * Définit le nom affiché sur la 2e ligne de l'écran d'accueil
     * (nom de la société ou du point de vente, fourni par le POS).
     */
    setStoreName(name) {
        if (name) {
            this.storeName = String(name).trim();
        }
    }

    // ── Compatibilité ─────────────────────────────────────────────────────────

    isApiSupported() {
        return 'serial' in navigator;
    }

    isSecureContext() {
        return Boolean(window.isSecureContext);
    }

    // ── Connexion ─────────────────────────────────────────────────────────────

    /**
     * Reconnexion automatique sur un port déjà autorisé (aucun geste requis).
     * @returns {Promise<boolean>}
     */
    async tryAutoConnect() {
        if (!this.isApiSupported() || !this.isSecureContext()) return false;
        try {
            const ports = await navigator.serial.getPorts();
            if (ports.length > 0) {
                return await this._openPort(ports[0]);
            }
        } catch (e) {
            console.warn('[BixolonDisplay] Auto-connect échoué :', e);
        }
        return false;
    }

    /**
     * Connexion manuelle — nécessite un geste utilisateur (clic bouton).
     * @returns {Promise<{success: boolean, reason: string|null}>}
     *   reason: 'no_serial_api' | 'not_secure_context' | 'no_port_selected' | 'open_error'
     */
    async connect() {
        if (!this.isApiSupported()) {
            return { success: false, reason: 'no_serial_api' };
        }
        if (!this.isSecureContext()) {
            return { success: false, reason: 'not_secure_context' };
        }
        try {
            const port = await navigator.serial.requestPort();
            const ok   = await this._openPort(port);
            return { success: ok, reason: ok ? null : 'open_error' };
        } catch (e) {
            if (e.name === 'NotFoundError') {
                return { success: false, reason: 'no_port_selected' };
            }
            console.error('[BixolonDisplay] connect() :', e);
            return { success: false, reason: 'open_error' };
        }
    }

    async _openPort(port) {
        try {
            await port.open({
                baudRate: this.BAUD_RATE,
                dataBits: 8,
                stopBits: 1,
                parity:   'none',
            });
            this.port        = port;
            this.writer      = port.writable.getWriter();
            this.isConnected = true;
            console.info('[BixolonDisplay] Port ouvert.');
            await this.sendWelcome();
            return true;
        } catch (e) {
            console.error('[BixolonDisplay] Impossible d\'ouvrir le port :', e);
            this.isConnected = false;
            return false;
        }
    }

    async disconnect() {
        if (!this.isConnected) return;
        try {
            await this.clear();
            this.writer.releaseLock();
            await this.port.close();
            console.info('[BixolonDisplay] Port fermé.');
        } catch (e) {
            console.warn('[BixolonDisplay] Erreur fermeture :', e);
        } finally {
            this.port        = null;
            this.writer      = null;
            this.isConnected = false;
            this._writing    = false;
        }
    }

    // ── Écriture (avec verrou anti-concurrence) ───────────────────────────────

    async _write(bytes) {
        if (!this.isConnected || !this.writer || this._writing) return;
        this._writing = true;
        try {
            await this.writer.write(bytes);
        } catch (e) {
            console.error('[BixolonDisplay] Erreur écriture :', e);
            this.isConnected = false;
        } finally {
            this._writing = false;
        }
    }

    async clear() {
        await this._write(new Uint8Array([0x0C]));
    }

    /**
     * Envoie 2 lignes sur l'afficheur.
     *
     * Le BCD-2000 ne comprend pas les séquences ANSI/VT100 (ESC[2;1H...) :
     * il les affiche telles quelles comme du texte brut (ex. "←[2;1H1x …"),
     * ce qui pollue l'écran. On compte donc sur le retour à la ligne
     * automatique du VFD après 20 caractères (comportement standard d'un
     * afficheur 2×20), sans tenter de positionner le curseur explicitement.
     *
     * Séquence envoyée : 0x0C (clear + curseur ligne 1 col 1)
     *                    + ligne1 (20 caractères) + ligne2 (20 caractères)
     */
    async sendDisplay(line1, line2) {
        if (!this.isConnected) return;
        const l1  = this._formatLine(line1);
        const l2  = this._formatLine(line2);
        const enc = new TextEncoder();
        const cmd = '\x0C' + l1 + l2;
        await this._write(enc.encode(cmd));
    }

    async sendWelcome() {
        await this.sendDisplay(
            this._centerLine('BIENVENUE !'),
            this._centerLine(this.storeName)
        );
    }

    // ── Formatage (ASCII propre pour VFD) ────────────────────────────────────

    /**
     * Nettoie une chaîne pour l'afficheur VFD (ASCII strict) :
     *  1. translittère les caractères Unicode courants des montants/textes
     *     formatés par Odoo (espaces insécables, symbole €, guillemets…)
     *     en équivalents ASCII via CHAR_REPLACEMENTS — évite les '?' parasites
     *     dans les prix (ex. "5 893 F CFA" au lieu de "5?893?F?CFA") ;
     *  2. supprime les diacritiques (accents) via décomposition NFD ;
     *  3. remplace tout caractère non-ASCII restant par '?'.
     */
    _sanitizeText(text) {
        let cleaned = String(text);
        for (const [from, to] of Object.entries(CHAR_REPLACEMENTS)) {
            cleaned = cleaned.split(from).join(to);
        }
        return cleaned
            .normalize('NFD')
            .replace(/[\u0300-\u036F]/g, '')   // supprime les combining diacritical marks
            .replace(/[^\x00-\x7F]/g, '?');    // remplace tout caractère non-ASCII restant
    }

    /** Formate une chaîne en exactement WIDTH caractères ASCII, alignée à gauche. */
    _formatLine(text) {
        if (!text) return ' '.repeat(this.WIDTH);
        return this._sanitizeText(text).substring(0, this.WIDTH).padEnd(this.WIDTH);
    }

    /** Formate une chaîne en exactement WIDTH caractères ASCII, centrée. */
    _centerLine(text) {
        const clean = this._sanitizeText(text).substring(0, this.WIDTH);
        const pad = Math.floor((this.WIDTH - clean.length) / 2);
        return (' '.repeat(pad) + clean).padEnd(this.WIDTH);
    }

    // ── Mise à jour depuis le POS ─────────────────────────────────────────────

    /**
     * Appelé depuis le patch CustomerDisplayPosAdapter.dispatch().
     * `data` = structure de CustomerDisplayPosAdapter.data :
     *   { finalized, amount, change, paymentLines, lines: [{productName, qty, unitPrice, price}] }
     */
    updateFromPOSData(data) {
        if (!this.isConnected) return;

        // 1. Commande finalisée → rendu monnaie
        if (data.finalized) {
            const change = data.change || '';
            this.sendDisplay(
                this._centerLine('*** MERCI ! ***'),
                this._formatLine('Rendu : ' + change)
            );
            return;
        }

        // 2. Paiement en cours → total à payer
        if (data.paymentLines && data.paymentLines.length > 0) {
            this.sendDisplay(
                this._formatLine('TOTAL A PAYER :'),
                this._centerLine(data.amount || '')
            );
            return;
        }

        // 3. Lignes en cours → dernier article scanné
        if (data.lines && data.lines.length > 0) {
            const last = data.lines[data.lines.length - 1];
            const name = last.productName || '';
            const qty  = String(last.qty  || '');
            const prix = last.unitPrice || last.price || '';
            this.sendDisplay(
                this._formatLine(name),
                this._formatLine(qty + 'x ' + prix)
            );
            return;
        }

        // 4. Commande vide → message d'accueil
        this.sendWelcome();
    }
}

// Singleton partagé entre bixolon_service et bixolon_pos_patch
export const bixolonDisplay = new BixolonDisplayManager();
