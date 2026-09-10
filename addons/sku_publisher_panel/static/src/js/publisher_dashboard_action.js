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
            activeTab: "candidates",
            syncProgress: null,
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

    selectTab(tab) {
        this.state.activeTab = tab;
    }

    get tabs() {
        const candidates = this.state.candidates || {};
        const jobs = this.state.jobs || {};
        const counters = jobs.counters || {};
        return [
            {
                key: "candidates",
                label: "Candidatos",
                value: candidates.total,
                error: Boolean(candidates.error),
            },
            { key: "jobs", label: "Procesos", value: jobs.total, error: Boolean(jobs.error) },
            {
                key: "items",
                label: "Ítems publicados",
                value: counters.items,
                error: Boolean(jobs.error),
            },
        ];
    }

    get activeTabError() {
        const tab = this.tabs.find((entry) => entry.key === this.state.activeTab);
        if (!tab || !tab.error) {
            return "";
        }
        return this.state.activeTab === "candidates"
            ? this.state.candidates.error
            : this.state.jobs.error;
    }

    // Estado del catalogo, sin lo pendiente de publicar.
    get candidateStats() {
        const candidates = this.state.candidates || {};
        return [
            { label: "Con stock", value: candidates.in_stock },
            { label: "Activos en ML", value: candidates.active },
            { label: "Con cuotas", value: candidates.premium },
        ].filter((row) => Number.isFinite(Number(row.value)));
    }

    // Lo accionable: cuanto falta publicar en cada marketplace.
    get candidatePending() {
        const candidates = this.state.candidates || {};
        const total = Number(candidates.total) || 0;
        return (candidates.pending || []).map((pending) => ({
            label: this.marketplaceLabel(pending.marketplace),
            value: pending.total,
            share: total ? Math.round(((Number(pending.total) || 0) / total) * 100) : 0,
            total,
        }));
    }

    get jobBreakdown() {
        const byStatus = (this.state.jobs || {}).by_status || {};
        const total = Object.values(byStatus).reduce((sum, value) => sum + (Number(value) || 0), 0);
        return Object.entries(byStatus)
            .sort((a, b) => b[1] - a[1])
            .map(([status, value]) => ({
                label: this.statusLabel(status),
                value,
                tone: this.statusTone(status),
                share: total ? Math.round(((Number(value) || 0) / total) * 100) : 0,
            }));
    }

    get itemBreakdown() {
        const counters = (this.state.jobs || {}).counters || {};
        const total = Number(counters.items) || 0;
        const share = (value) => (total ? Math.round(((Number(value) || 0) / total) * 100) : 0);
        return [
            { label: "Publicados", value: counters.done, tone: "is-green", share: share(counters.done) },
            { label: "Con error", value: counters.error, tone: "is-red", share: share(counters.error) },
            { label: "En cola", value: counters.queued, tone: "is-blue", share: share(counters.queued) },
            { label: "Omitidos", value: counters.skipped, tone: "is-gray", share: share(counters.skipped) },
        ].filter((row) => Number.isFinite(Number(row.value)));
    }

    get syncPercent() {
        const progress = this.state.syncProgress;
        if (!progress || !progress.total) {
            return 0;
        }
        return Math.min(100, Math.round((progress.processed / progress.total) * 100));
    }

    // El refresh se encadena por tandas para poder informar avance; en un solo
    // paso eran ~1.400 upserts sin ninguna senal de vida.
    async syncCandidates() {
        this.state.syncing = "candidates";
        this.state.syncProgress = { processed: 0, total: 0 };
        try {
            const run = await this.orm.call("publisher.sku", "refresh_candidates_start", []);
            const batchSize = run.batchSize || 100;
            this.state.syncProgress.total = run.total || 0;

            let offset = 0;
            let created = 0;
            let updated = 0;
            // Tope defensivo: sin el, un "done" que nunca llega cuelga la pestana.
            for (let guard = 0; guard < 500; guard++) {
                const batch = await this.orm.call("publisher.sku", "refresh_candidates_batch", [], {
                    offset,
                    limit: batchSize,
                });
                created += batch.created || 0;
                updated += batch.updated || 0;
                this.state.syncProgress.processed = batch.processed || 0;
                if (batch.total) {
                    this.state.syncProgress.total = batch.total;
                }
                if (batch.done) {
                    break;
                }
                offset += batchSize;
            }

            const finish = await this.orm.call("publisher.sku", "refresh_candidates_finish", [], {
                started_at: run.startedAt,
            });
            this.notification.add(
                `Candidatos sincronizados: ${created} nuevos, ${updated} actualizados, ${finish.removed || 0} eliminados.`,
                { type: "success" }
            );
            await this.loadOverview();
        } catch (error) {
            this.notification.add(
                error?.data?.message || "No se pudo sincronizar los candidatos.",
                { type: "danger" }
            );
        } finally {
            this.state.syncing = "";
            this.state.syncProgress = null;
        }
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
        if (key === "candidates") {
            return this.syncCandidates();
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
