/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const JOB_STATUS_LABELS = {
    queued: "En cola",
    processing: "Procesando",
    completed: "Completado",
    completed_with_errors: "Con errores",
    failed: "Fallido",
    cancelled: "Cancelado",
    unknown: "Sin estado",
};

const JOB_STATUS_TONE = {
    completed: "is-green",
    completed_with_errors: "is-amber",
    failed: "is-red",
    cancelled: "is-gray",
    queued: "is-blue",
    processing: "is-blue",
};

const MARKETPLACE_LABELS = {
    oncity: "OnCity",
    fravega: "Fravega",
    megatone: "Megatone",
};

class PublisherDashboardAction extends Component {
    static template = "sku_publisher_panel.DashboardAction";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            syncing: "",
            candidates: {},
            jobs: {},
        });
        onWillStart(() => this.loadOverview());
    }

    async loadOverview() {
        this.state.loading = true;
        try {
            const overview = await this.orm.call(
                "publisher.dashboard",
                "get_dashboard_overview",
                []
            );
            this.state.candidates = overview.candidates || {};
            this.state.jobs = overview.jobs || {};
        } catch (error) {
            this.notification.add("No se pudo cargar el resumen del publicador.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    // Metricas que acompanan a cada numero grande.
    get candidateBreakdown() {
        const candidates = this.state.candidates;
        if (candidates.error) {
            return [];
        }
        const rows = [
            { label: "Con stock", value: candidates.in_stock },
            { label: "Activos en ML", value: candidates.active },
            { label: "Con cuotas", value: candidates.premium },
        ];
        for (const pending of candidates.pending || []) {
            rows.push({
                label: `Sin publicar en ${this.marketplaceLabel(pending.marketplace)}`,
                value: pending.total,
                tone: "is-warning",
            });
        }
        return rows.filter((row) => Number.isFinite(Number(row.value)));
    }

    get jobBreakdown() {
        const byStatus = (this.state.jobs || {}).by_status || {};
        return Object.entries(byStatus)
            .sort((a, b) => b[1] - a[1])
            .map(([status, value]) => ({
                label: this.statusLabel(status),
                value,
                tone: JOB_STATUS_TONE[status] === "is-red" ? "is-warning" : "",
            }));
    }

    get itemBreakdown() {
        const counters = (this.state.jobs || {}).counters || {};
        return [
            { label: "Publicados", value: counters.done },
            { label: "Con error", value: counters.error, tone: counters.error ? "is-warning" : "" },
            { label: "En cola", value: counters.queued },
            { label: "Omitidos", value: counters.skipped },
        ].filter((row) => Number.isFinite(Number(row.value)));
    }

    statusLabel(status) {
        return JOB_STATUS_LABELS[status] || this.titleize(status);
    }

    statusTone(status) {
        return JOB_STATUS_TONE[status] || "is-gray";
    }

    marketplaceLabel(name) {
        return MARKETPLACE_LABELS[name] || this.titleize(name);
    }

    titleize(value) {
        const text = String(value || "").replace(/[_-]+/g, " ").trim();
        return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
    }

    formatNumber(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value) || 0);
    }

    formatDateTime(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        }).format(date);
    }

    jobProgress(job) {
        const total = Number(job.total) || 0;
        if (!total) {
            return 0;
        }
        return Math.round(((Number(job.done) || 0) / total) * 100);
    }

    shortJobId(jobId) {
        const text = String(jobId || "");
        return text.length > 18 ? `${text.slice(0, 8)}...${text.slice(-6)}` : text;
    }

    async openCandidates() {
        await this.action.doAction("sku_publisher_panel.action_publisher_candidates_cards");
    }

    async openJobs() {
        await this.action.doAction("sku_publisher_panel.action_publisher_job");
    }

    async openRuns() {
        await this.action.doAction("sku_publisher_panel.action_publisher_run");
    }

    // Las sincronizaciones siguen existiendo porque llenan las tablas locales
    // que usan las vistas de lista; el resumen ya no depende de ellas.
    async sync(key) {
        const targets = {
            candidates: ["publisher.sku", "action_refresh_candidates"],
            jobs: ["publisher.job", "action_sync_recent_jobs"],
            runs: ["publisher.job.line", "action_sync_runs"],
        };
        const target = targets[key];
        if (!target || this.state.syncing) {
            return;
        }
        this.state.syncing = key;
        try {
            const result = await this.orm.call(target[0], target[1], []);
            if (result && result.params && result.params.message) {
                this.notification.add(result.params.message, {
                    type: result.params.type || "success",
                });
            }
            await this.loadOverview();
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo sincronizar.",
                { type: "danger" }
            );
        } finally {
            this.state.syncing = "";
        }
    }
}

registry.category("actions").add("sku_publisher_panel.dashboard_action", PublisherDashboardAction);
