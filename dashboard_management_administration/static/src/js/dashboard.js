/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DashboardManagementAdmin extends Component {

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.evolutionChartRef = useRef("evolutionChart");
        this.repartitionChartRef = useRef("repartitionChart");
        this.topClientsChartRef = useRef("topClientsChart");

        this.evolutionChart = null;
        this.repartitionChart = null;
        this.topClientsChart = null;

        this.state = useState({
            data: null,
            dateFrom: this._defaultDateFrom(),
            dateTo: this._defaultDateTo(),
            loading: true,
        });

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            this.renderCharts();
        });
    }

    /* ===================== DATES ===================== */

    // _defaultDateFrom() {
    //     const d = new Date();
    //     d.setDate(d.getDate() - 30);
    //     return d.toISOString().split("T")[0];
    // }

    _defaultDateFrom() {
        const d = new Date();
        d.setDate(1);  // premier jour du mois
        return d.toISOString().split("T")[0];
    }

    _defaultDateTo() {
        return new Date().toISOString().split("T")[0];
    }

    /* ===================== LOAD ===================== */

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "dashboard.management.admin",
                "get_dashboard_data",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                }
            );
            this.state.data = data;

            setTimeout(() => this.renderCharts(), 100);
        } catch (err) {
            console.error("Dashboard load error:", err);
        } finally {
            this.state.loading = false;
        }
    }

    async onFilterChange(ev) {
        const field = ev.target.dataset.field;
        this.state[field] = ev.target.value;
        await this.loadData();
    }

    /* ===================== CHARTS ===================== */

    renderCharts() {
        if (!this.state.data || this.state.loading) return;

        this._destroyCharts();
        this._renderEvolutionChart();
        this._renderRepartitionChart();
        this._renderTopClientsChart();
    }

    _destroyCharts() {
        this.evolutionChart?.destroy();
        this.repartitionChart?.destroy();
        this.topClientsChart?.destroy();
    }

    _renderEvolutionChart() {
        const ctx = this.evolutionChartRef.el?.getContext("2d");
        if (!ctx) return;

        const data = this.state.data.evolution_ventes || [];
        const labels = data.map(d => d.date);
        const ventes = data.map(d => d.ventes);
        const pos = data.map(d => d.pos);

        this.evolutionChart = new Chart(ctx, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Vente: Gros",
                        data: ventes,
                        borderColor: "#2196f3",
                        backgroundColor: "rgba(33,150,243,.15)",
                        fill: true,
                        tension: 0.4,
                    },
                    {
                        label: "POS: 1/2 Gros",
                        data: pos,
                        borderColor: "#ff9800",
                        backgroundColor: "rgba(255,152,0,.15)",
                        fill: true,
                        tension: 0.4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: ctx =>
                                `${ctx.dataset.label}: ${this.formatCurrency(ctx.parsed.y)}`,
                        },
                    },
                },
                scales: {
                    y: {
                        ticks: {
                            callback: v => this.formatCurrency(v),
                        },
                    },
                },
            },
        });
    }

    _renderRepartitionChart() {
        const ctx = this.repartitionChartRef.el?.getContext("2d");
        if (!ctx) return;

        const s = this.state.data.statistiques;

        this.repartitionChart = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: ["Vente: Gros", "POS: 1/2 Gros", "Achats"],
                datasets: [{
                    data: [s.total_ventes, s.total_pos, s.total_achats],
                    backgroundColor: ["#2196f3", "#ff9800", "#e91e63"],
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: ctx =>
                                `${ctx.label}: ${this.formatCurrency(ctx.parsed)}`,
                        },
                    },
                },
            },
        });
    }

    _renderTopClientsChart() {
        const ctx = this.topClientsChartRef.el?.getContext("2d");
        if (!ctx) return;

        const clients = this.state.data.top_clients || [];

        this.topClientsChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: clients.map(c => c.name),
                datasets: [{
                    label: "Chiffre d'affaires",
                    data: clients.map(c => c.total),
                    backgroundColor: "#4caf50",
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: ctx =>
                                this.formatCurrency(ctx.parsed.y),
                        },
                    },
                },
                scales: {
                    y: {
                        ticks: {
                            callback: v => this.formatCurrency(v),
                        },
                    },
                },
            },
        });
    }

    /* ===================== ACTIONS ===================== */

    openListView(model, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Détails",
            res_model: model,
            domain: domain,
            views: [[false, "list"], [false, "form"]],
            target: "current",
        });
    }

    /* ===================== FORMAT ===================== */

    formatCurrency(amount) {
        return new Intl.NumberFormat("fr-FR").format(amount || 0) + " FCFA";
    }

    formatPercent(val) {
        return (val || 0).toFixed(2) + " %";
    }
}

/* ===================== REGISTRY ===================== */

DashboardManagementAdmin.template = "dashboard_management_admin.Dashboard";

registry
    .category("actions")
    .add("dashboard_management_admin", DashboardManagementAdmin);
