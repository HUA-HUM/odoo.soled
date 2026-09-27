/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "coresa.catalog";

class CoresaCatalogAction extends Component {
    static template = "coresa_panel.CatalogAction";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.state = useState({
            items: [],
            brands: [],
            total: 0,
            limit: 48,
            offset: 0,
            filters: { search: "", marca: "", subFamilia: "", sku: "", disponible: "" },
            detail: null,
            // Por SKU, no por posicion: la seleccion sobrevive al paginado.
            selected: {},
            run: { active: false, cancel: false, done: 0, total: 0, results: {} },
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

    get selectedSkus() {
        return Object.keys(this.state.selected).filter((sku) => this.state.selected[sku]);
    }

    get allSelected() {
        return (
            this.state.items.length > 0 &&
            this.state.items.every((item) => this.state.selected[item.sku])
        );
    }

    get progressPercent() {
        const run = this.state.run;
        return run.total ? Math.round((run.done / run.total) * 100) : 0;
    }

    get runSummary() {
        const results = Object.values(this.state.run.results);
        return {
            ready: results.filter((one) => one.state === "ready").length,
            draft: results.filter((one) => one.state === "draft").length,
            failed: results.filter((one) => one.state === "failed").length,
        };
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

    // Algunas imagenes del bucket de Coresa dan 403 (hoy, toda la carpeta
    // DCK). Sin esto el navegador deja el icono de imagen rota.
    onImageError(item) {
        item.imageFailed = true;
    }

    openDetail(item) {
        this.state.detail = item;
    }

    // ------------------------------------------------------------------
    // Mandar al publicador
    // ------------------------------------------------------------------
    toggle(item, ev) {
        if (ev) {
            // La tarjeta entera abre la ficha: el check no tiene que abrirla.
            ev.stopPropagation();
        }
        if (this.state.run.active) {
            return;
        }
        this.state.selected[item.sku] = !this.state.selected[item.sku];
    }

    toggleAll() {
        if (this.state.run.active) {
            return;
        }
        const select = !this.allSelected;
        for (const item of this.state.items) {
            this.state.selected[item.sku] = select;
        }
    }

    clearSelection() {
        this.state.selected = {};
    }

    resultFor(item) {
        return this.state.run.results[item.sku] || null;
    }

    resultLabel(state) {
        const labels = {
            queued: "En cola",
            working: "Armando...",
            ready: "Listo para publicar",
            draft: "Borrador",
            failed: "Con error",
            cancelled: "Cancelado",
        };
        return labels[state] || state;
    }

    sendSelected() {
        const skus = this.selectedSkus;
        if (!skus.length) {
            this.notification.add("Elegí al menos un producto.", { type: "warning" });
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: skus.length === 1 ? "Mandar al publicador" : `Mandar ${skus.length} al publicador`,
            body:
                `Se arma el borrador de ${skus.length === 1 ? "este SKU" : `estos ${skus.length} SKU`}: ` +
                "categoría, atributos y el texto del aviso. No publica nada en MercadoLibre. " +
                "Si un SKU ya tenía borrador, se rehace. " +
                `Van de a uno: ${this.estimate(skus.length)}.`,
            confirmLabel: "Armar borradores",
            cancelLabel: "Cancelar",
            confirm: () => this.runSend(skus),
        });
    }

    // De a uno, esperando cada respuesta: el preview encadena Coresa,
    // MercadoLibre y la redaccion, y no conviene dispararlos en paralelo.
    async runSend(skus) {
        const run = this.state.run;
        Object.assign(run, { active: true, cancel: false, done: 0, total: skus.length, results: {} });
        for (const sku of skus) {
            run.results[sku] = { state: "queued", detail: "" };
        }

        for (const sku of skus) {
            if (run.cancel) {
                run.results[sku].state = "cancelled";
                continue;
            }
            run.results[sku].state = "working";
            try {
                const result = await this.orm.call(MODEL, "send_to_publisher", [sku]);
                const state = result.status === "ready" ? "ready" : "draft";
                run.results[sku] = {
                    state,
                    detail:
                        state === "ready"
                            ? "MercadoLibre lo acepta."
                            : result.missing.length
                            ? `Faltan atributos: ${result.missing.join(", ")}`
                            : "MercadoLibre todavía no lo acepta.",
                };
            } catch (error) {
                run.results[sku] = {
                    state: "failed",
                    detail: error?.data?.message || "No se pudo armar el borrador.",
                };
            }
            run.done += 1;
        }

        run.active = false;
        const summary = this.runSummary;
        this.notification.add(
            `${summary.ready} listos para publicar, ${summary.draft} en borrador` +
                (summary.failed ? `, ${summary.failed} con error` : "") + ".",
            { type: summary.failed ? "warning" : "success" }
        );
        this.state.selected = {};
    }

    // Medido contra produccion: el preview tarda entre 4 y 10 segundos.
    estimate(count) {
        const seconds = count * 10;
        if (seconds < 60) {
            return `unos ${seconds} segundos en total`;
        }
        const minutes = Math.round(seconds / 60);
        return `unos ${minutes} minuto${minutes === 1 ? "" : "s"} en total`;
    }

    cancelRun() {
        this.state.run.cancel = true;
        this.notification.add("Se corta cuando termine el que está en curso.", { type: "info" });
    }

    async openPublisher() {
        await this.action.doAction("coresa_meli_publisher.action_coresa_publisher");
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
