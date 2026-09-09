/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "retailer.marketplace.change";

class RetailerBulkActionsAction extends Component {
    static template = "retailer_marketplace_panel.BulkActionsAction";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            runs: [],
            runsLimit: 20,
            runsOffset: 0,
            runsTotal: 0,
            runsLoading: false,
            runsError: "",
            runsFilters: { processName: "", status: "", triggerType: "" },
            runningReconciliation: false,
            runningSync: false,
        });
        onWillStart(() => this.loadProcessRuns(0));
    }

    get runsHasPrevious() {
        return this.state.runsOffset > 0;
    }

    get runsHasNext() {
        return this.state.runsOffset + this.state.runsLimit < this.state.runsTotal;
    }

    get isBusy() {
        return this.state.runningReconciliation || this.state.runningSync;
    }

    async loadProcessRuns(offset = this.state.runsOffset) {
        this.state.runsLoading = true;
        this.state.runsError = "";
        try {
            const result = await this.orm.call(MODEL, "get_process_runs_page", [], {
                limit: this.state.runsLimit,
                offset,
                process_name: this.state.runsFilters.processName || false,
                status: this.state.runsFilters.status || false,
                trigger_type: this.state.runsFilters.triggerType || false,
            });
            this.state.runs = result.items || [];
            this.state.runsOffset = result.pagination.offset || 0;
            this.state.runsTotal = result.pagination.total || 0;
        } catch (error) {
            this.state.runsError = "No pudimos cargar las ejecuciones.";
            this.notification.add(this.state.runsError, { type: "danger" });
        } finally {
            this.state.runsLoading = false;
        }
    }

    applyRunsFilters(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.loadProcessRuns(0);
    }

    resetRunsFilters() {
        Object.assign(this.state.runsFilters, { processName: "", status: "", triggerType: "" });
        this.loadProcessRuns(0);
    }

    get hasRunsFilters() {
        return Object.values(this.state.runsFilters).some((value) => Boolean(value));
    }

    previousRunsPage() {
        if (this.runsHasPrevious) {
            this.loadProcessRuns(Math.max(0, this.state.runsOffset - this.state.runsLimit));
        }
    }

    nextRunsPage() {
        if (this.runsHasNext) {
            this.loadProcessRuns(this.state.runsOffset + this.state.runsLimit);
        }
    }

    async runProcess(key) {
        const targets = {
            reconciliation: ["action_run_meli_reconciliation", "runningReconciliation", "No se pudo ejecutar la reconciliación."],
            sync: ["action_run_catalog_sync", "runningSync", "No se pudo ejecutar el sync."],
        };
        const target = targets[key];
        if (!target || this.isBusy) {
            return;
        }
        const [method, flag, errorMessage] = target;
        this.state[flag] = true;
        try {
            const result = await this.orm.call(MODEL, method, []);
            if (result && result.params && result.params.message) {
                this.notification.add(result.params.message, {
                    type: result.params.type || "success",
                });
            }
            await this.loadProcessRuns(0);
        } catch (error) {
            this.notification.add(error?.data?.message || errorMessage, { type: "danger" });
        } finally {
            this.state[flag] = false;
        }
    }

    runReconciliationNow() {
        return this.runProcess("reconciliation");
    }

    runCatalogSyncNow() {
        return this.runProcess("sync");
    }

    statusClass(status) {
        const value = (status || "").toLowerCase();
        if (value.includes("fail") || value.includes("error")) {
            return "is-failed";
        }
        if (value.includes("complet") || value.includes("success") || value.includes("done")) {
            return "is-completed";
        }
        return "is-pending";
    }

    statusLabel(status) {
        const value = (status || "").toLowerCase();
        if (value.includes("fail") || value.includes("error")) {
            return "Con error";
        }
        if (value.includes("complet") || value.includes("success") || value.includes("done")) {
            return "Completado";
        }
        if (value.includes("running") || value.includes("process")) {
            return "Corriendo";
        }
        return status || "Sin estado";
    }

    triggerLabel(value) {
        return { cron: "Automático", manual: "Manual", api: "API" }[value] || value || "—";
    }

    processLabel(value) {
        return (
            {
                meli_reconciliation: "Reconciliación MELI",
                marketplace_publications_sync: "Sync de catálogo",
            }[value] || value || "—"
        );
    }

    // El summary llega como objeto libre y varia por proceso: el sync anida
    // {marketplaces: [...]} y la reconciliacion trae contadores planos. Sin
    // aplanar el array, las corridas de sync mostraban "—".
    runSummaryText(run) {
        const summary = run && run.summary;
        if (!summary || typeof summary !== "object") {
            return (run && run.errorMessage) || "—";
        }
        const parts = [];
        for (const [key, value] of Object.entries(summary)) {
            if (value === null || value === undefined) {
                continue;
            }
            if (Array.isArray(value)) {
                const nested = value
                    .filter((entry) => entry && typeof entry === "object")
                    .map((entry) => {
                        const name = entry.marketplace || entry.name || "";
                        const count = entry.productsSynced ?? entry.total;
                        return name && count !== undefined ? `${name} ${count}` : name;
                    })
                    .filter(Boolean);
                if (nested.length) {
                    parts.push(nested.join(" · "));
                }
                continue;
            }
            if (typeof value === "object") {
                continue;
            }
            parts.push(`${this.summaryLabel(key)} ${value}`);
        }
        return parts.length ? parts.join(" · ") : (run && run.errorMessage) || "—";
    }

    summaryLabel(key) {
        return (
            {
                publicationsChecked: "Revisadas",
                meliItemsChecked: "Items MELI",
                correctionsQueued: "Correcciones",
                meliLookupErrors: "Errores",
                productsSynced: "Sincronizados",
                productsFound: "Encontrados",
            }[key] || key
        );
    }

    formatDate(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(typeof value === "string" ? value.replace(" ", "T") : value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(date);
    }

    formatDuration(value) {
        if (value === null || value === undefined) {
            return "—";
        }
        const milliseconds = Number(value) || 0;
        if (milliseconds < 1000) {
            return `${Math.round(milliseconds)} ms`;
        }
        return `${new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1 }).format(milliseconds / 1000)} s`;
    }
}

registry.category("actions").add("retailer_marketplace_panel.bulk_actions_action", RetailerBulkActionsAction);
