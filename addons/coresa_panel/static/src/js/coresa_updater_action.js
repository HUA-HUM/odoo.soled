/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "coresa.updater";

class CoresaUpdaterAction extends Component {
    static template = "coresa_panel.UpdaterAction";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            items: [],
            total: 0,
            limit: 24,
            offset: 0,
            // updateStock y updatePrice van vacios o "true"/"false": la API
            // los recibe como string.
            filters: { sku: "", mla: "", updateStock: "", updatePrice: "" },
            summary: { total: 0, skus: 0, stock: 0, price: 0 },
            detail: null,
            detailSku: "",
            loading: false,
            loadingDetail: false,
            error: "",
        });

        onWillStart(async () => {
            await this.loadPage(0);
            this.loadSummary();
        });

        this._onKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.detail) {
                this.closeDetail();
            }
        };
        window.addEventListener("keydown", this._onKeydown);
        onWillUnmount(() => window.removeEventListener("keydown", this._onKeydown));
    }

    // ------------------------------------------------------------------
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

    get hasFilters() {
        return Object.values(this.state.filters).some((value) => Boolean(value));
    }

    get rangeLabel() {
        if (!this.state.total) {
            return "0";
        }
        const from = this.state.offset + 1;
        const to = Math.min(this.state.offset + this.state.limit, this.state.total);
        return `${from}–${to} de ${this.formatUnits(this.state.total)}`;
    }

    // ------------------------------------------------------------------
    async loadSummary() {
        try {
            this.state.summary = await this.orm.call(MODEL, "get_updater_summary", []);
        } catch (error) {
            // El encabezado es informativo: si falla, la grilla sigue.
            this.state.summary = { total: 0, skus: 0, stock: 0, price: 0 };
        }
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "get_updater_page", [], {
                limit: this.state.limit,
                offset,
                filters: { ...this.state.filters },
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.total = result.pagination.total || 0;
        } catch (error) {
            this.state.items = [];
            this.state.total = 0;
            this.state.error =
                error?.data?.message || "No se pudo leer lo que el actualizador tiene publicado.";
        } finally {
            this.state.loading = false;
        }
    }

    applyFilters(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.loadPage(0);
    }

    resetFilters() {
        Object.assign(this.state.filters, {
            sku: "",
            mla: "",
            updateStock: "",
            updatePrice: "",
        });
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

    // ------------------------------------------------------------------
    async openDetail(row) {
        this.state.detailSku = row.sku;
        this.state.detail = null;
        this.state.loadingDetail = true;
        try {
            this.state.detail = await this.orm.call(MODEL, "get_sku_detail", [row.sku, row.mla]);
        } catch (error) {
            this.state.detail = {
                sku: row.sku,
                product: null,
                meli: null,
                publications: [],
                changes: [],
                errors: [error?.data?.message || "No se pudo cargar la ficha del SKU."],
            };
        } finally {
            this.state.loadingDetail = false;
        }
    }

    closeDetail() {
        this.state.detail = null;
        this.state.detailSku = "";
        this.state.loadingDetail = false;
    }

    openLink(url, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        if (url) {
            window.open(url, "_blank", "noopener");
        }
    }

    // Igual que en el catalogo: parte del bucket de Coresa responde 403 y sin
    // esto queda el icono de imagen rota.
    onImageError(row) {
        row.imageFailed = true;
    }

    // ------------------------------------------------------------------
    formatUnits(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value) || 0);
    }

    formatArs(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric) || !numeric) {
            return "—";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: "ARS",
            maximumFractionDigits: 0,
        }).format(numeric);
    }

    formatList(value, currency) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric) || !numeric) {
            return "—";
        }
        return `${currency || ""} ${new Intl.NumberFormat("es-AR", {
            maximumFractionDigits: 2,
        }).format(numeric)}`.trim();
    }

    formatDate(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        return date.toLocaleDateString("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
    }

    formatDateTime(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        return date.toLocaleString("es-AR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    stockTone(value) {
        const units = Number(value) || 0;
        if (!units) {
            return "is-out";
        }
        return units < 10 ? "is-low" : "is-ok";
    }

    meliStatusLabel(status) {
        const labels = {
            active: "Activa",
            paused: "Pausada",
            closed: "Cerrada",
            under_review: "En revisión",
            inactive: "Inactiva",
        };
        return labels[status] || status || "—";
    }

    changeResultLabel(result) {
        const labels = {
            updated: "Actualizado",
            not_applied: "Sin cambios",
            failed: "Falló",
        };
        return labels[result] || result || "—";
    }

    // El stock de Coresa contra el publicado en ML: es el numero que el
    // actualizador tiene que emparejar.
    stockGap(detail) {
        if (!detail || !detail.product || !detail.meli) {
            return null;
        }
        return Number(detail.meli.available || 0) - Number(detail.product.available || 0);
    }

    // La frase se arma aca: el template no tiene Math y ademas hay que
    // singularizar.
    gapMessage(detail) {
        const gap = this.stockGap(detail);
        if (gap === null) {
            return "";
        }
        if (gap === 0) {
            return "El stock publicado coincide con el de Coresa.";
        }
        const size = Math.abs(gap);
        const units = size === 1 ? "unidad" : "unidades";
        const side = gap > 0 ? "de más" : "de menos";
        return `En MercadoLibre hay ${this.formatUnits(size)} ${units} ${side} que en Coresa.`;
    }
}

registry.category("actions").add("coresa_panel.updater_action", CoresaUpdaterAction);
