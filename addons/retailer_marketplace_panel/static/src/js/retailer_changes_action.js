/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "retailer.marketplace.change";

class RetailerChangesAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            items: [],
            limit: 24,
            offset: 0,
            total: 0,
            sku: "",
            marketplace: "",
            status: "",
            loading: false,
            syncingAll: false,
            error: "",
        });
        onWillStart(() => this.loadPage());
    }

    get currentPage() {
        return Math.floor(this.state.offset / this.state.limit) + 1;
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.state.total / this.state.limit));
    }

    get hasPrevious() {
        return this.state.offset > 0;
    }

    get hasNext() {
        return this.state.offset + this.state.limit < this.state.total;
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
        if (value.includes("process")) {
            return "Procesando";
        }
        if (value.includes("queue") || value.includes("pend")) {
            return "Pendiente";
        }
        return status || "Sin estado";
    }

    get completedCount() {
        return this.state.items.filter((item) => this.statusClass(item.status) === "is-completed").length;
    }

    get failedCount() {
        return this.state.items.filter((item) => this.statusClass(item.status) === "is-failed").length;
    }

    formatDate(value) {
        if (!value) {
            return "";
        }
        const normalized = typeof value === "string" ? value.replace(" ", "T") : value;
        const date = new Date(normalized);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            dateStyle: "short",
            timeStyle: "short",
        }).format(date);
    }

    compactValue(value) {
        if (!value) {
            return "—";
        }
        const text = String(value).replace(/\s+/g, " ").trim();
        return text.length > 90 ? `${text.slice(0, 87)}…` : text;
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "get_changes_page", [], {
                limit: this.state.limit,
                offset,
                sku: this.state.sku || false,
                marketplace: this.state.marketplace || false,
                status: this.state.status || false,
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.limit = result.pagination.limit || this.state.limit;
            this.state.total = result.pagination.total || 0;
        } catch (error) {
            this.state.error = "No pudimos cargar los cambios. Revisá la conexión o reintentá en unos segundos.";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async searchChanges(ev) {
        ev.preventDefault();
        await this.loadPage(0);
    }

    clearSearch() {
        this.state.sku = "";
        this.state.marketplace = "";
        this.state.status = "";
        this.loadPage(0);
    }

    previousPage() {
        if (this.hasPrevious) {
            this.loadPage(Math.max(0, this.state.offset - this.state.limit));
        }
    }

    nextPage() {
        if (this.hasNext) {
            this.loadPage(this.state.offset + this.state.limit);
        }
    }

    async syncAllChanges() {
        this.state.syncingAll = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "action_sync_all", []);
            if (result && result.params && result.params.message) {
                this.notification.add(result.params.message, { type: result.params.type || "success" });
            }
            await this.loadPage(0);
        } catch (error) {
            this.state.error = "No se pudo completar la sincronización.";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.syncingAll = false;
        }
    }

    openDetail(item) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: item.id,
            views: [[false, "form"]],
            target: "new",
        });
    }
}

RetailerChangesAction.template = "retailer_marketplace_panel.ChangesAction";

registry.category("actions").add("retailer_marketplace_panel.changes_action", RetailerChangesAction);
