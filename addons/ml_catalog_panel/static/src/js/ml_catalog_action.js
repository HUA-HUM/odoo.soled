/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "ml.catalog";

const STATUS = {
    active: { label: "Activa", tone: "is-green" },
    paused: { label: "Pausada", tone: "is-amber" },
    closed: { label: "Cerrada", tone: "is-red" },
    under_review: { label: "En revisión", tone: "is-blue" },
    inactive: { label: "Inactiva", tone: "is-gray" },
};

const LISTING_TYPES = {
    gold_special: "Clásica",
    gold_pro: "Premium",
    free: "Gratuita",
};

const CONDITIONS = { new: "Nuevo", used: "Usado", not_specified: "Sin especificar" };

const SHIPPING_MODES = { me2: "Mercado Envíos", me1: "Mercado Envíos 1", custom: "A convenir" };

class MlCatalogAction extends Component {
    static template = "ml_catalog_panel.CatalogAction";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            items: [],
            page: 1,
            limit: 36,
            total: 0,
            totalPages: 0,
            pageInput: "1",
            // Busqueda exacta: la API resuelve SKU o MLA, no texto libre.
            search: "",
            searching: false,
            notFound: "",
            detail: null,
            detailId: "",
            loadingDetail: false,
            loading: false,
            error: "",
        });

        onWillStart(() => this.loadPage(1));

        this._onKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.detail) {
                this.closeDetail();
            }
        };
        window.addEventListener("keydown", this._onKeydown);
        onWillUnmount(() => window.removeEventListener("keydown", this._onKeydown));
    }

    get hasPrevious() {
        return this.state.page > 1 && !this.state.searching;
    }

    get hasNext() {
        return this.state.page < this.state.totalPages && !this.state.searching;
    }

    // Un SKU puede tener varias publicaciones: la busqueda las trae todas.
    get searchLabel() {
        const count = this.state.items.length;
        const noun = count === 1 ? "publicación" : "publicaciones";
        return `${this.formatUnits(count)} ${noun} con ${this.state.search.trim()}`;
    }

    get rangeLabel() {
        if (!this.state.total) {
            return "0";
        }
        const from = (this.state.page - 1) * this.state.limit + 1;
        const to = Math.min(this.state.page * this.state.limit, this.state.total);
        return `${from}–${to} de ${this.formatUnits(this.state.total)}`;
    }

    async loadPage(page = this.state.page) {
        this.state.loading = true;
        this.state.error = "";
        this.state.notFound = "";
        try {
            const result = await this.orm.call(MODEL, "get_catalog_page", [], {
                page,
                limit: this.state.limit,
            });
            this.state.items = result.items || [];
            this.state.page = result.pagination.page || page;
            this.state.pageInput = String(this.state.page);
            this.state.total = result.pagination.total || 0;
            this.state.totalPages = result.pagination.totalPages || 0;
            this.state.searching = false;
        } catch (error) {
            this.state.items = [];
            this.state.error =
                error?.data?.message || "No se pudo leer el catálogo de MercadoLibre.";
        } finally {
            this.state.loading = false;
        }
    }

    previousPage() {
        if (this.hasPrevious) {
            this.loadPage(this.state.page - 1);
        }
    }

    nextPage() {
        if (this.hasNext) {
            this.loadPage(this.state.page + 1);
        }
    }

    goToPage(ev) {
        if (ev) {
            ev.preventDefault();
        }
        const page = Math.min(
            Math.max(1, parseInt(this.state.pageInput, 10) || 1),
            this.state.totalPages || 1
        );
        this.loadPage(page);
    }

    // La API no busca por texto: resuelve un identificador. Se avisa cuando
    // no existe, en vez de devolver una grilla vacia que parece un filtro.
    async runSearch(ev) {
        if (ev) {
            ev.preventDefault();
        }
        const query = this.state.search.trim();
        if (!query) {
            this.loadPage(1);
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        this.state.notFound = "";
        try {
            const result = await this.orm.call(MODEL, "find_product", [query]);
            this.state.items = result.items || [];
            this.state.searching = true;
            if (!result.found) {
                this.state.notFound = query;
            }
        } catch (error) {
            this.state.items = [];
            this.state.error = error?.data?.message || "No se pudo buscar.";
        } finally {
            this.state.loading = false;
        }
    }

    clearSearch() {
        this.state.search = "";
        this.loadPage(1);
    }

    async openDetail(item) {
        this.state.detailId = item.id;
        this.state.detail = null;
        this.state.loadingDetail = true;
        try {
            this.state.detail = await this.orm.call(MODEL, "get_product_detail", [item.id]);
        } catch (error) {
            this.state.detail = null;
            this.state.loadingDetail = false;
            this.state.error = error?.data?.message || "No se pudo abrir la publicación.";
            return;
        }
        this.state.loadingDetail = false;
    }

    closeDetail() {
        this.state.detail = null;
        this.state.detailId = "";
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

    onImageError(item) {
        item.imageFailed = true;
    }

    // ------------------------------------------------------------------
    statusLabel(status) {
        return (STATUS[status] || {}).label || status || "—";
    }

    statusTone(status) {
        return (STATUS[status] || {}).tone || "is-gray";
    }

    listingLabel(listingType) {
        return LISTING_TYPES[listingType] || listingType || "—";
    }

    conditionLabel(condition) {
        return CONDITIONS[condition] || condition || "—";
    }

    shippingLabel(detail) {
        if (!detail || !detail.shippingMode) {
            return "—";
        }
        const mode = SHIPPING_MODES[detail.shippingMode] || detail.shippingMode;
        return detail.freeShipping ? `${mode} · envío gratis` : mode;
    }

    stockTone(value) {
        const units = Number(value) || 0;
        if (!units) {
            return "is-out";
        }
        return units < 10 ? "is-low" : "is-ok";
    }

    formatMoney(value) {
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

    formatUnits(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value) || 0);
    }

    formatDateTime(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        return new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(date);
    }
}

registry.category("actions").add("ml_catalog_panel.catalog_action", MlCatalogAction);
