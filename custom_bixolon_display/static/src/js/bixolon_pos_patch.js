/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

import { CustomerDisplayPosAdapter } from "@point_of_sale/app/customer_display/customer_display_adapter";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";

import { bixolonDisplay } from "@custom_bixolon_display/js/bixolon_service";

// ── Patch CustomerDisplayPosAdapter ──────────────────────────────────────────
// Intercepte chaque mise à jour du customer display Odoo et relaie sur le BCD-2000.

patch(CustomerDisplayPosAdapter.prototype, {
    dispatch(pos) {
        super.dispatch(pos);
        if (pos.config?.has_bixolon_display) {
            bixolonDisplay.updateFromPOSData(this.data);
        }
    },
});


// ── Patch Navbar ──────────────────────────────────────────────────────────────
// Ajoute l'état réactif OWL et le bouton de connexion à l'afficheur.

patch(Navbar.prototype, {

    setup() {
        super.setup();

        // État réactif OWL — nécessaire pour que le template se re-rende
        // automatiquement quand la connexion change.
        this.bixolonState = useState({ connected: false });

        if (this.pos.config?.has_bixolon_display) {
            // Tentative de reconnexion automatique (port déjà autorisé)
            bixolonDisplay.tryAutoConnect().then((connected) => {
                this.bixolonState.connected = connected;
                if (connected) {
                    this.notification.add(
                        _t('Afficheur Bixolon BCD-2000 connecté.'),
                        { type: 'success', title: _t('Afficheur') }
                    );
                }
            });
        }
    },

    // ── Getters ───────────────────────────────────────────────────────────────

    get hasBixolonDisplay() {
        return Boolean(this.pos.config?.has_bixolon_display);
    },

    /** Reactive via useState — le template se met à jour automatiquement. */
    get bixolonConnected() {
        return this.bixolonState?.connected || false;
    },

    // ── Bouton Connecter / Déconnecter ────────────────────────────────────────

    async onClickBixolonConnect() {

        // 1. Déjà connecté → déconnecter
        if (bixolonDisplay.isConnected) {
            await bixolonDisplay.disconnect();
            this.bixolonState.connected = false;
            this.notification.add(
                _t('Afficheur Bixolon déconnecté.'),
                { type: 'info', title: _t('Afficheur') }
            );
            return;
        }

        // 2. Web Serial API absente (navigateur non supporté)
        if (!bixolonDisplay.isApiSupported()) {
            this.dialog.add(AlertDialog, {
                title: _t('Navigateur non supporté'),
                body:  _t('Utilisez Microsoft Edge ou Google Chrome (version 89+) pour l\'afficheur Bixolon.'),
            });
            return;
        }

        // 3. Contexte non sécurisé (HTTP sans flag Edge) → guide pas-à-pas
        if (!bixolonDisplay.isSecureContext()) {
            this.dialog.add(AlertDialog, {
                title: _t('Configuration Edge requise'),
                body: _t(
                    'L\'accès au port série requiert une exception dans Edge.\n\n' +
                    'Étapes (une seule fois par PC) :\n' +
                    '1. Ouvrir un nouvel onglet Edge\n' +
                    '2. Coller dans la barre d\'adresse :\n' +
                    '   edge://flags/#unsafely-treat-insecure-origin-as-secure\n' +
                    '3. Dans le champ texte, entrer :\n' +
                    '   http://172.16.8.178:8089\n' +
                    '4. Mettre le menu déroulant sur "Enabled"\n' +
                    '5. Cliquer "Relaunch"\n' +
                    '6. Revenir sur le POS et recliquer Afficheur.'
                ),
            });
            return;
        }

        // 4. Connexion normale — ouverture de la boîte de sélection du port
        this.notification.add(
            _t('Sélectionnez le port COM du BCD-2000 dans la fenêtre qui s\'ouvre…'),
            { type: 'info', title: _t('Afficheur') }
        );

        const result = await bixolonDisplay.connect();

        if (result.success) {
            this.bixolonState.connected = true;
            this.notification.add(
                _t('Afficheur Bixolon BCD-2000 connecté !'),
                { type: 'success', title: _t('Afficheur') }
            );
            return;
        }

        // 5. Échec avec message adapté
        const errMessages = {
            no_port_selected: _t('Aucun port sélectionné. Réessayez et choisissez le port COM du BCD-2000.'),
            open_error:       _t('Impossible d\'ouvrir le port. Vérifiez que le driver Bixolon est installé et le câble USB branché.'),
        };
        this.notification.add(
            errMessages[result.reason] || _t('Échec de la connexion à l\'afficheur.'),
            { type: 'danger', title: _t('Afficheur Bixolon') }
        );
    },
});
