/** @odoo-module **/

/**
 * BixolonDisplayManager — communication série avec le Bixolon BCD-2000
 * via Web Serial API (Edge/Chrome 89+).
 *
 * Protocole VFD Bixolon BCD-2000 (2 lignes × 20 caractères) :
 *   0x0C              = Effacer l'écran + curseur en ligne 1, col 1
 *   \x1B[2;1H         = Positionner curseur en ligne 2, col 1 (séquence ANSI)
 *   Baud : 9600, 8 bits, pas de parité, 1 stop bit
 */
class BixolonDisplayManager {
    constructor() {
        this.port        = null;
        this.writer      = null;
        this.isConnected = false;
        this._writing    = false;   // verrou : évite les écritures concurrentes
        this.BAUD_RATE   = 9600;
        this.WIDTH       = 20;
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
     * Envoie 2 lignes sur l'afficheur avec positionnement ANSI explicite.
     * Plus fiable que l'auto-wrap qui dépend de la config interne du BCD-2000.
     *
     * Séquence : 0x0C (clear) + ligne1 (20 chars) + ESC[2;1H (cursor→ligne2) + ligne2 (20 chars)
     */
    async sendDisplay(line1, line2) {
        if (!this.isConnected) return;
        const l1  = this._formatLine(line1);
        const l2  = this._formatLine(line2);
        const enc = new TextEncoder();
        // ESC [ 2 ; 1 H = positionne le curseur en ligne 2, colonne 1
        const cmd = '\x0C' + l1 + '\x1B[2;1H' + l2;
        await this._write(enc.encode(cmd));
    }

    async sendWelcome() {
        await this.sendDisplay('   BIENVENUE !      ', '   SANGEL YOP SARL  ');
    }

    // ── Formatage (ASCII propre pour VFD) ────────────────────────────────────

    /**
     * Formate une chaîne en exactement WIDTH caractères ASCII.
     * Supprime les diacritiques (accents) incompatibles avec la plupart des VFD.
     */
    _formatLine(text) {
        if (!text) return ' '.repeat(this.WIDTH);
        const ascii = String(text)
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')   // supprime les combining diacritical marks
            .replace(/[^\x00-\x7F]/g, '?');    // remplace tout caractère non-ASCII restant
        return ascii.substring(0, this.WIDTH).padEnd(this.WIDTH);
    }

    _centerLine(text) {
        const clean = String(text)
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')
            .replace(/[^\x00-\x7F]/g, '?')
            .substring(0, this.WIDTH);
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
