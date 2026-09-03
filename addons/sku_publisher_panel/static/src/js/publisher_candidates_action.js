/** @odoo-module **/

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DEFAULT_FILTERS = {
    listingType: "all",
    brand: "all",
    category: "all",
    stock: "all",
    status: "all",
    publishedIn: "all",
    notPublishedIn: "all",
    sortBy: "updated_at",
    sortDir: "desc",
};

const FILTER_META = {
    listingType: { label: "Tipo", options: "listingTypes" },
    brand: { label: "Marca", options: "brands" },
    category: { label: "Categoria", options: "categories" },
    stock: { label: "Stock", options: "stock" },
    status: { label: "Estado", options: "statuses" },
    publishedIn: { label: "Publicado en", marketplace: true },
    notPublishedIn: { label: "Sin publicar en", marketplace: true },
};

const MARKETPLACE_LABELS = {
    oncity: "OnCity",
    fravega: "Fravega",
    megatone: "Megatone",
};

class PublisherCandidatesAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            items: [],
            marketplaces: ["oncity", "fravega"],
            selected: {},
            limit: 24,
            offset: 0,
            total: 0,
            search: "",
            // Destino de publicacion, no es un filtro del listado.
            marketplace: "both",
            filters: { ...DEFAULT_FILTERS },
            options: {
                brands: [],
                categories: [],
                listingTypes: [],
                statuses: [],
                stock: [],
            },
            optionsError: "",
            detailSku: false,
            loading: false,
            publishing: false,
        });
        onWillStart(async () => {
            await Promise.all([this.loadFilterOptions(), this.loadPage()]);
        });

        this._onKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.detailSku) {
                this.closeDetail();
            }
        };
        onMounted(() => window.addEventListener("keydown", this._onKeydown));
        onWillUnmount(() => window.removeEventListener("keydown", this._onKeydown));
    }

    get selectedSkus() {
        return Object.entries(this.state.selected)
            .filter((entry) => entry[1])
            .map((entry) => entry[0]);
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

    get activeFilters() {
        const filters = {};
        const search = String(this.state.search || "").trim();
        if (search) {
            filters.search = search;
        }
        for (const [key, value] of Object.entries(this.state.filters)) {
            if (value && value !== "all") {
                filters[key] = value;
            }
        }
        return filters;
    }

    async loadFilterOptions() {
        try {
            const options = await this.orm.call("publisher.sku", "get_candidate_filters", []);
            this.state.options = {
                brands: options.brands || [],
                categories: options.categories || [],
                listingTypes: options.listingTypes || [],
                statuses: options.statuses || [],
                stock: options.stock || [],
            };
            this.state.optionsError = "";
        } catch (error) {
            // Sin combos se puede seguir filtrando por busqueda y orden.
            this.state.optionsError = "No se pudieron cargar las opciones de filtro.";
        }
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        try {
            const result = await this.orm.call("publisher.sku", "get_candidates_page", [], {
                limit: this.state.limit,
                offset,
                filters: this.activeFilters,
            });
            this.state.items = result.items || [];
            this.state.marketplaces = result.marketplaces || this.state.marketplaces;
            this.state.offset = result.pagination.offset || 0;
            this.state.limit = result.pagination.limit || this.state.limit;
            this.state.total = result.pagination.total || 0;
            this.state.selected = {};
            this.state.detailSku = false;
        } finally {
            this.state.loading = false;
        }
    }

    async searchSku(ev) {
        ev.preventDefault();
        await this.loadPage(0);
    }

    changeFilter() {
        this.loadPage(0);
    }

    // Resumen de lo aplicado, para que los selects puedan ser compactos sin
    // que el usuario pierda de vista que hay filtros puestos.
    get activeFilterChips() {
        const chips = [];
        const search = String(this.state.search || "").trim();
        if (search) {
            chips.push({ key: "search", label: "Busqueda", value: search });
        }
        for (const [key, meta] of Object.entries(FILTER_META)) {
            const value = this.state.filters[key];
            if (!value || value === DEFAULT_FILTERS[key]) {
                continue;
            }
            let text = value;
            if (meta.marketplace) {
                text = this.marketplaceLabel(value);
            } else {
                const match = (this.state.options[meta.options] || []).find(
                    (option) => option.value === value
                );
                text = match ? match.label : value;
            }
            chips.push({ key, label: meta.label, value: text });
        }
        return chips;
    }

    clearFilter(key) {
        if (key === "search") {
            this.state.search = "";
        } else {
            this.state.filters[key] = DEFAULT_FILTERS[key];
        }
        this.loadPage(0);
    }

    // El orden se elige con un solo select ("precio:asc") y se parte en los
    // dos parametros que espera la API.
    get sortValue() {
        return `${this.state.filters.sortBy}:${this.state.filters.sortDir}`;
    }

    changeSort(ev) {
        const [sortBy, sortDir] = String(ev.target.value || "").split(":");
        this.state.filters.sortBy = sortBy || DEFAULT_FILTERS.sortBy;
        this.state.filters.sortDir = sortDir || DEFAULT_FILTERS.sortDir;
        this.loadPage(0);
    }

    clearSearch() {
        this.state.search = "";
        this.loadPage(0);
    }

    get hasActiveFilters() {
        if (String(this.state.search || "").trim()) {
            return true;
        }
        return Object.entries(this.state.filters).some(
            ([key, value]) => value !== DEFAULT_FILTERS[key]
        );
    }

    resetFilters() {
        this.state.search = "";
        Object.assign(this.state.filters, DEFAULT_FILTERS);
        this.loadPage(0);
    }

    marketplaceLabel(name) {
        return MARKETPLACE_LABELS[name] || this.titleize(name);
    }

    titleize(value) {
        const text = String(value || "").replace(/[_-]+/g, " ").trim();
        return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
    }

    isPublishedIn(item, marketplace) {
        return Boolean((item.marketplaces || {})[marketplace]);
    }

    formatPriceRange(item) {
        const min = Number(item.price_min);
        const max = Number(item.price_max);
        if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
            return "";
        }
        return `${this.formatMoney(min)} - ${this.formatMoney(max)}`;
    }

    formatMoney(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
            return "-";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: "ARS",
            maximumFractionDigits: 2,
        }).format(numeric);
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

    toggleSku(sku) {
        this.state.selected[sku] = !this.state.selected[sku];
    }

    openDetail(sku) {
        this.state.detailSku = sku;
    }

    closeDetail() {
        this.state.detailSku = false;
    }

    get detailItem() {
        if (!this.state.detailSku) {
            return null;
        }
        return this.state.items.find((item) => item.sku === this.state.detailSku) || null;
    }

    formatBool(value) {
        return value ? "Si" : "No";
    }

    openPermalink(item) {
        if (item.permalink) {
            window.open(item.permalink, "_blank", "noopener");
        }
    }

    selectPage() {
        const shouldSelect = this.selectedSkus.length !== this.state.items.length;
        for (const item of this.state.items) {
            this.state.selected[item.sku] = shouldSelect;
        }
    }

    marketplacesForPublish() {
        if (this.state.marketplace === "both") {
            return ["oncity", "fravega"];
        }
        return [this.state.marketplace];
    }

    async publishSelected() {
        const skus = this.selectedSkus;
        if (!skus.length) {
            this.notification.add("Selecciona al menos una card.", { type: "warning" });
            return;
        }
        this.state.publishing = true;
        try {
            const action = await this.orm.call("publisher.sku", "publish_skus", [], {
                skus,
                marketplaces: this.marketplacesForPublish(),
            });
            await this.action.doAction(action);
        } finally {
            this.state.publishing = false;
        }
    }
}

PublisherCandidatesAction.template = "sku_publisher_panel.CandidatesAction";

registry.category("actions").add("sku_publisher_panel.candidates_action", PublisherCandidatesAction);
