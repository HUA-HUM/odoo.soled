/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "coresa.publication";

// Los estados los define la API: el panel no inventa ni traduce a otros.
const STATUSES = [
    { key: "draft", label: "Borrador", tone: "is-gray" },
    { key: "ready", label: "Listo", tone: "is-blue" },
    { key: "publishing", label: "Publicando", tone: "is-blue" },
    { key: "published", label: "Publicado", tone: "is-green" },
    { key: "partial", label: "Parcial", tone: "is-amber" },
    { key: "failed", label: "Con error", tone: "is-red" },
    { key: "discarded", label: "Descartado", tone: "is-muted" },
];

const STATUS_BY_KEY = Object.fromEntries(STATUSES.map((s) => [s.key, s]));

class CoresaPublicationsAction extends Component {
    static template = "coresa_meli_publisher.PublicationsAction";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            items: [],
            counters: {},
            total: 0,
            limit: 25,
            offset: 0,
            filters: { status: "", sku: "", from: "", to: "" },
            loading: false,
            error: "",
        });
        onWillStart(async () => {
            await Promise.all([this.loadPage(0), this.loadCounters()]);
        });
    }

    get statuses() {
        return STATUSES;
    }

    get totalAll() {
        return Object.values(this.state.counters).reduce((sum, n) => sum + (Number(n) || 0), 0);
    }

    get hasFilters() {
        return Object.values(this.state.filters).some((value) => Boolean(value));
    }

    get hasPrevious() {
        return this.state.offset > 0;
    }

    get hasNext() {
        return this.state.offset + this.state.limit < this.state.total;
    }

    get rangeLabel() {
        if (!this.state.total) {
            return "0";
        }
        const from = this.state.offset + 1;
        const to = Math.min(this.state.offset + this.state.limit, this.state.total);
        return `${from}–${to} de ${this.state.total}`;
    }

    async loadCounters() {
        try {
            this.state.counters = await this.orm.call(MODEL, "get_publication_counters", []);
        } catch (error) {
            this.state.counters = {};
        }
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "get_publications_page", [], {
                limit: this.state.limit,
                offset,
                filters: { ...this.state.filters },
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.total = result.pagination.total || 0;
        } catch (error) {
            this.state.items = [];
            this.state.error =
                error?.data?.message || "No se pudieron cargar las publicaciones.";
        } finally {
            this.state.loading = false;
        }
    }

    selectStatus(status) {
        this.state.filters.status = this.state.filters.status === status ? "" : status;
        this.loadPage(0);
    }

    applyFilters(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.loadPage(0);
    }

    resetFilters() {
        Object.assign(this.state.filters, { status: "", sku: "", from: "", to: "" });
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

    async openPublication(item) {
        try {
            const action = await this.orm.call(MODEL, "open_publication", [], {
                publication_id: item.id,
            });
            await this.action.doAction(action);
        } catch (error) {
            // El mensaje generico esconde la causa, que es lo unico util para
            // arreglarlo: va el detalle de Odoo cuando existe.
            const detail = error?.data?.message || error?.message || "";
            this.notification.add(
                detail
                    ? `No se pudo abrir la publicación: ${detail}`
                    : "No se pudo abrir la publicación.",
                { type: "danger", sticky: true }
            );
        }
    }

    async newPublication() {
        await this.action.doAction("coresa_meli_publisher.action_coresa_publication_wizard");
    }

    openMeli(itemId, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        if (itemId) {
            window.open(`https://articulo.mercadolibre.com.ar/${itemId}`, "_blank", "noopener");
        }
    }

    statusLabel(status) {
        return (STATUS_BY_KEY[status] || {}).label || status || "—";
    }

    statusTone(status) {
        return (STATUS_BY_KEY[status] || {}).tone || "is-gray";
    }

    counterFor(status) {
        return Number(this.state.counters[status]) || 0;
    }

    formatMoney(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
            return "—";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: "ARS",
            maximumFractionDigits: 0,
        }).format(numeric);
    }

    formatUnits(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value) || 0);
    }

    formatDate(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return new Intl.DateTimeFormat("es-AR", {
            dateStyle: "short",
            timeStyle: "short",
        }).format(date);
    }
}

registry
    .category("actions")
    .add("coresa_meli_publisher.publications_action", CoresaPublicationsAction);
