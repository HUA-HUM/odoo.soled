/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "coresa.catalog";

class CoresaCatalogAction extends Component {
    static template = "coresa_panel.CatalogAction";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            items: [],
            brands: [],
            total: 0,
            limit: 48,
            offset: 0,
            filters: { search: "", marca: "", subFamilia: "", sku: "", disponible: "" },
            detail: null,
            loading: false,
            loadingBrands: false,
            error: "",
        });

        onWillStart(() => this.loadPage(0));
        // Las marcas exigen recorrer las 5.400 filas: se piden aparte para no
        // demorar la grilla.
        onMounted(() => this.loadBrands());

        this._onKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.detail) {
                this.closeDetail();
            }
        };
        window.addEventListener("keydown", this._onKeydown);
        onWillUnmount(() => window.removeEventListener("keydown", this._onKeydown));
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

    get hasFilters() {
        return Object.values(this.state.filters).some((value) => Boolean(value));
    }

    async loadBrands() {
        this.state.loadingBrands = true;
        try {
            const facets = await this.orm.call(MODEL, "get_catalog_facets", []);
            this.state.brands = facets.brands || [];
        } catch (error) {
            this.state.brands = [];
        } finally {
            this.state.loadingBrands = false;
        }
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "get_catalog_page", [], {
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
                error?.data?.message || "No se pudo cargar el catálogo de Coresa.";
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

    selectBrand() {
        this.loadPage(0);
    }

    resetFilters() {
        Object.assign(this.state.filters, {
            search: "",
            marca: "",
            subFamilia: "",
            sku: "",
            disponible: "",
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

    openDetail(item) {
        this.state.detail = item;
    }

    closeDetail() {
        this.state.detail = null;
    }

    openLink(url, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        if (url) {
            window.open(url, "_blank", "noopener");
        }
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
            return "";
        }
        return `${currency || ""} ${new Intl.NumberFormat("es-AR", {
            maximumFractionDigits: 2,
        }).format(numeric)}`.trim();
    }

    formatUnits(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value) || 0);
    }

    stockTone(value) {
        const units = Number(value) || 0;
        if (!units) {
            return "is-out";
        }
        return units < 10 ? "is-low" : "is-ok";
    }
}

registry.category("actions").add("coresa_panel.catalog_action", CoresaCatalogAction);
