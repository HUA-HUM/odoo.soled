/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "coresa.updater";

// Los tres cortes con los que se revisa esto. La API recibe las banderas
// como string, no como booleano.
const VIEWS = {
    all: {},
    synced: { updateStock: "true", updatePrice: "true" },
    excluded: { updateStock: "false", updatePrice: "false" },
};

/** Formato y helpers que comparten las dos pestañas. */
class UpdaterBase extends Component {
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

    // Algunas imagenes del bucket de Coresa dan 403 (hoy, toda la carpeta
    // DCK). Sin esto el navegador deja el icono de imagen rota.
    onImageError(row) {
        row.imageFailed = true;
    }
}

/* ------------------------------------------------------------------ */
/* Pestaña 1: el catalogo publicado                                    */
/* ------------------------------------------------------------------ */
class UpdaterCatalogTab extends UpdaterBase {
    static template = "coresa_panel.UpdaterCatalogTab";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            items: [],
            total: 0,
            limit: 24,
            offset: 0,
            filters: { sku: "", mla: "", updateStock: "", updatePrice: "" },
            detail: null,
            detailSku: "",
            loading: false,
            loadingDetail: false,
            error: "",
        });

        onWillStart(() => this.loadPage(0));

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

    get rangeLabel() {
        if (!this.state.total) {
            return "0";
        }
        const from = this.state.offset + 1;
        const to = Math.min(this.state.offset + this.state.limit, this.state.total);
        return `${from}–${to} de ${this.formatUnits(this.state.total)}`;
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
}

/* ------------------------------------------------------------------ */
/* Pestaña 2: que mira el actualizador y que le toca                   */
/* ------------------------------------------------------------------ */
class UpdaterActionsTab extends UpdaterBase {
    static template = "coresa_panel.UpdaterActionsTab";
    static props = { onChanged: { type: Function, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            items: [],
            total: 0,
            limit: 24,
            offset: 0,
            view: "all",
            search: { sku: "", mla: "" },
            counters: { all: 0, synced: 0, excluded: 0 },
            form: { open: false, sku: "", mla: "", updateStock: true, updatePrice: true, saving: false },
            // MLA esperando respuesta: deshabilita esa fila sola.
            busy: "",
            loading: false,
            error: "",
        });

        onWillStart(() => this.loadPage(0));
        onMounted(() => this.loadCounters());
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

    get rangeLabel() {
        if (!this.state.total) {
            return "0";
        }
        const from = this.state.offset + 1;
        const to = Math.min(this.state.offset + this.state.limit, this.state.total);
        return `${from}–${to} de ${this.formatUnits(this.state.total)}`;
    }

    // Cuando se filtra por un SKU con varias publicaciones conviene poder
    // cambiarlas todas juntas: es el caso clasica + premium.
    get skuBulk() {
        const sku = (this.state.search.sku || "").trim();
        if (!sku || this.state.total < 2) {
            return null;
        }
        return { sku, total: this.state.total };
    }

    async loadCounters() {
        try {
            this.state.counters = await this.orm.call(MODEL, "get_actions_counters", []);
        } catch (error) {
            this.state.counters = { all: 0, synced: 0, excluded: 0 };
        }
    }

    currentFilters() {
        const filters = { ...VIEWS[this.state.view] };
        if (this.state.search.sku.trim()) {
            filters.sku = this.state.search.sku.trim();
        }
        if (this.state.search.mla.trim()) {
            filters.mla = this.state.search.mla.trim();
        }
        return filters;
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "get_updater_page", [], {
                limit: this.state.limit,
                offset,
                filters: this.currentFilters(),
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.total = result.pagination.total || 0;
        } catch (error) {
            this.state.items = [];
            this.state.total = 0;
            this.state.error = error?.data?.message || "No se pudo leer la lista.";
        } finally {
            this.state.loading = false;
        }
    }

    setView(view) {
        this.state.view = view;
        this.loadPage(0);
    }

    applySearch(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.loadPage(0);
    }

    resetSearch() {
        this.state.search.sku = "";
        this.state.search.mla = "";
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
    // Lo que cambia de verdad
    // ------------------------------------------------------------------

    // Apagar una bandera no toca nada en MercadoLibre: solo evita cambios
    // futuros. Conviene decirlo, porque no es obvio.
    flagNotice(field, value) {
        const what = field === "updatePrice" ? "precio" : "stock";
        if (value) {
            return `Vuelve a sincronizar ${what} en la próxima corrida del actualizador.`;
        }
        return `Deja de recibir actualizaciones de ${what}. El ${what} que tiene hoy en MercadoLibre queda como está.`;
    }

    async toggleFlag(row, field) {
        if (this.state.busy) {
            return;
        }
        const value = !row[field];
        this.state.busy = row.mla;
        try {
            const updated = await this.orm.call(MODEL, "set_publication_flags", [row.mla], {
                update_stock: field === "updateStock" ? value : null,
                update_price: field === "updatePrice" ? value : null,
            });
            row.updateStock = updated.updateStock;
            row.updatePrice = updated.updatePrice;
            this.notification.add(this.flagNotice(field, value), {
                title: `${row.sku} · ${row.mla}`,
                type: value ? "success" : "warning",
            });
            this.afterChange();
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo cambiar la bandera.", {
                type: "danger",
            });
        } finally {
            this.state.busy = "";
        }
    }

    removeFromUpdater(row) {
        this.dialog.add(ConfirmationDialog, {
            title: "Sacar del actualizador",
            body:
                `${row.sku} · ${row.mla} deja de recibir actualizaciones de precio y de stock. ` +
                "Lo que hoy está publicado en MercadoLibre queda como está: esto solo evita cambios futuros.",
            confirmLabel: "Sacar del actualizador",
            cancelLabel: "Cancelar",
            confirm: () => this.applyBoth(row, false),
        });
    }

    async applyBoth(row, value) {
        this.state.busy = row.mla;
        try {
            const updated = await this.orm.call(MODEL, "set_publication_flags", [row.mla], {
                update_stock: value,
                update_price: value,
            });
            row.updateStock = updated.updateStock;
            row.updatePrice = updated.updatePrice;
            this.notification.add(
                value
                    ? "Vuelve a sincronizar precio y stock."
                    : "Ya no se sincroniza. Lo publicado en MercadoLibre queda como está.",
                { title: `${row.sku} · ${row.mla}`, type: value ? "success" : "warning" }
            );
            this.afterChange();
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo cambiar la publicación.", {
                type: "danger",
            });
        } finally {
            this.state.busy = "";
        }
    }

    applyToSku(value) {
        const bulk = this.skuBulk;
        if (!bulk) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: value ? "Sincronizar todo el SKU" : "Sacar todo el SKU",
            body: value
                ? `Las ${bulk.total} publicaciones de ${bulk.sku} vuelven a sincronizar precio y stock.`
                : `Las ${bulk.total} publicaciones de ${bulk.sku} dejan de recibir actualizaciones. ` +
                  "Lo que está publicado queda como está.",
            confirmLabel: value ? "Sincronizar todas" : "Sacar todas",
            cancelLabel: "Cancelar",
            confirm: async () => {
                this.state.loading = true;
                try {
                    const result = await this.orm.call(MODEL, "set_sku_flags", [bulk.sku], {
                        update_stock: value,
                        update_price: value,
                    });
                    this.notification.add(
                        `${result.updated} publicaciones de ${bulk.sku} actualizadas.`,
                        { type: value ? "success" : "warning" }
                    );
                    await this.loadPage(0);
                    this.afterChange();
                } catch (error) {
                    this.notification.add(error?.data?.message || "No se pudo cambiar el SKU.", {
                        type: "danger",
                    });
                } finally {
                    this.state.loading = false;
                }
            },
        });
    }

    // ------------------------------------------------------------------
    // Alta de un vinculo
    // ------------------------------------------------------------------
    toggleForm() {
        this.state.form.open = !this.state.form.open;
    }

    async createLink(ev) {
        if (ev) {
            ev.preventDefault();
        }
        const form = this.state.form;
        if (!form.sku.trim() || !form.mla.trim()) {
            this.notification.add("Hacen falta el SKU y la publicación (MLA).", { type: "warning" });
            return;
        }
        form.saving = true;
        try {
            const created = await this.orm.call(
                MODEL,
                "link_publication",
                [form.sku.trim(), form.mla.trim()],
                { update_stock: form.updateStock, update_price: form.updatePrice }
            );
            this.notification.add(
                form.updateStock || form.updatePrice
                    ? `${created.sku} · ${created.mla} entra al actualizador.`
                    : `${created.sku} · ${created.mla} queda registrado, sin sincronizar.`,
                { type: "success" }
            );
            Object.assign(form, { sku: "", mla: "", updateStock: true, updatePrice: true, open: false });
            await this.loadPage(0);
            this.afterChange();
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo registrar el vínculo.", {
                type: "danger",
            });
        } finally {
            form.saving = false;
        }
    }

    afterChange() {
        this.loadCounters();
        if (this.props.onChanged) {
            this.props.onChanged();
        }
    }
}

/* ------------------------------------------------------------------ */
/* El contenedor con las dos pestañas                                  */
/* ------------------------------------------------------------------ */
class CoresaUpdaterAction extends UpdaterBase {
    static template = "coresa_panel.UpdaterAction";
    static components = { UpdaterCatalogTab, UpdaterActionsTab };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            tab: "catalog",
            summary: { total: 0, skus: 0, stock: 0, price: 0 },
            loadingSummary: true,
        });

        // El resumen recorre las 432 filas y tarda ~1s: la pantalla se
        // dibuja primero y los numeros entran despues.
        onMounted(() => this.loadSummary());
    }

    async loadSummary() {
        this.state.loadingSummary = true;
        try {
            this.state.summary = await this.orm.call(MODEL, "get_updater_summary", []);
        } catch (error) {
            this.state.summary = { total: 0, skus: 0, stock: 0, price: 0 };
        } finally {
            this.state.loadingSummary = false;
        }
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    num(value) {
        return this.state.loadingSummary ? "—" : this.formatUnits(value);
    }
}

registry.category("actions").add("coresa_panel.updater_action", CoresaUpdaterAction);
