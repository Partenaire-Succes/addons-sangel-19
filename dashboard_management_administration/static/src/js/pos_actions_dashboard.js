/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class PosActionsDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        
        this.state = useState({
            data: null,
            loading: true,
            actionLoading: {},
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "pos.actions.dashboard",
                "get_dashboard_data",
                []
            );
            this.state.data = data;
        } catch (error) {
            console.error("Erreur lors du chargement des données:", error);
            this.notification.add("Erreur lors du chargement des données", {
                type: "danger"
            });
        } finally {
            this.state.loading = false;
        }
    }

    async executeAction(actionName, params = {}) {
        const actionKey = actionName;
        this.state.actionLoading[actionKey] = true;

        try {
            const result = await this.orm.call(
                "pos.actions.dashboard",
                actionName,
                [[]],
                params
            );
            console.log("Action retournée :", result);
            if (result && result.type) {
                await this.action.doAction(result);
            }

            await this.loadData();

        } catch (error) {
            console.error(`Erreur ${actionName}:`, error);

            this.notification.add(
                error?.data?.message || error.message || "Erreur serveur",
                { type: "danger" }
            );

        } finally {
            this.state.actionLoading[actionKey] = false;
        }
    }

    async onImportAllData() {
        if (confirm('Voulez-vous importer les produits et contacts ?')) {
            await this.executeAction('action_import_all_data');
        }
    }

    async onProcessDocuments() {
        if (confirm('Cette action enverra toutes les demandes d\'approvisionnement ainsi que les données comptables vers Sage X3. Êtes-vous sûr de vouloir continuer ?')) {
            await this.executeAction('action_process_documents');
        }
    }

    async onImportProducts() {
        try {
            const action = await this.orm.call(
                "pos.actions.dashboard",
                "action_import_products",
                [[]]
            );

            if (action) {
                await this.action.doAction(action);
            }

        } catch (error) {
            console.error("Erreur réelle :", error);
            this.notification.add(
                error.message || "Erreur lors de la synchronisation des produits",
                { type: "danger" }
            );
        }
    }

    async onImportContacts() {
        try {
            const action = await this.orm.call(
                "pos.actions.dashboard",
                "action_import_contacts",
                [[]]
            );

            if (action) {
                await this.action.doAction(action);
            }

        } catch (error) {
            console.error("Erreur réelle :", error);
            this.notification.add(
                error.message || "Erreur lors de la synchronisation des contacts",
                { type: "danger" }
            );
        }
    }

    async onValidatePurchases() {
        try {
            const action = await this.orm.call(
                "pos.actions.dashboard",
                "action_validate_purchases",
                [[]]
            );

            if (action) {
                await this.action.doAction(action);
            }

        } catch (error) {
            console.error("Erreur réelle :", error);
            this.notification.add(
                error.message || "Erreur lors de l'envoi des demandes d'approvisionnement",
                { type: "danger" }
            );
        }
    }

    async onReceivePurchases() {
        try {
            const action = await this.orm.call(
                "pos.actions.dashboard",
                "action_receive_purchases",
                [[]]
            );

            if (action) {
                await this.action.doAction(action);
            }

        } catch (error) {
            console.error("Erreur réelle :", error);
            this.notification.add(
                error.message || "Erreur lors de la réception des commandes",
                { type: "danger" }
            );
        }
    }


    async onSendInvoicesX3() {
        try {
            const action = await this.orm.call(
                "pos.actions.dashboard",
                "action_send_invoices_x3",
                [[]]
            );

            if (action) {
                await this.action.doAction(action);
            }

        } catch (error) {
            console.error("Erreur réelle :", error);
            this.notification.add(
                error.message || "Erreur lors de l'envoi des factures",
                { type: "danger" }
            );
        }
    }
    async onRefresh() {
        await this.loadData();
        this.notification.add("Données actualisées", { type: "success" });
    }

    getSessionStateClass(state) {
        const stateClasses = {
            'opening_control': 'warning',
            'opened': 'success',
            'closing_control': 'info',
            'closed': 'secondary',
        };
        return stateClasses[state] || 'secondary';
    }

    formatCurrency(amount) {
        if (!amount) return "0 FCFA";
        return new Intl.NumberFormat('fr-FR', {
            style: 'decimal',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount) + ' FCFA';
    }

    isActionLoading(actionName, params = {}) {
        const actionKey = JSON.stringify({ actionName, params });
        return this.state.actionLoading[actionKey] || false;
    }
}

PosActionsDashboard.template = "pos_actions_dashboard.Dashboard";

registry.category("actions").add("pos_actions_dashboard", PosActionsDashboard);
