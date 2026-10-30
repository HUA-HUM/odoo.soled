/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { PublicationsEmbedded } from "@coresa_meli_publisher/js/coresa_publications_action";
import { PublicationEditor } from "@coresa_meli_publisher/js/coresa_publication_editor";

const MODEL = "coresa.publication";

const CONDITIONS = { new: "Nuevo", used: "Usado", not_specified: "Sin especificar" };
const LISTING_TYPES = {
    gold_special: "Clásica",
    gold_pro: "Premium",
    free: "Gratuita",
};
const SHIPPING_MODES = { me2: "Mercado Envíos", me1: "Mercado Envíos 1", custom: "A convenir", not_specified: "Sin especificar" };

/* ------------------------------------------------------------------ */
/* Pestaña 1: armar y mirar el borrador                                */
/* ------------------------------------------------------------------ */
class PublisherPreviewTab extends Component {
    static template = "coresa_meli_publisher.PublisherPreviewTab";
    // Se puede llegar desde la cola con el SKU ya puesto.
    static props = { sku: { type: String, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            sku: this.props.sku || "",
            // La variante define el precio, el stock y la identidad de la
            // publicacion: el mismo SKU se publica varias veces distinto.
            variant: { listingType: "gold_special", units: 1, modalidad: "contado" },
            modalidades: [],
            // Paso 0: lo que Coresa tiene de ese SKU, para elegir las
            // unidades sabiendo con que se cuenta.
            skuInfo: null,
            lookingUp: false,
            data: null,
            loading: false,
            fixing: false,
            error: "",
            // La descripcion la escribe un modelo y es larga: arranca plegada.
            descriptionOpen: false,
        });

        onWillStart(async () => {
            try {
                this.state.modalidades = await this.orm.call(MODEL, "get_modalidades", []);
            } catch (error) {
                // Sin el desplegable igual se puede previsualizar en contado.
                this.state.modalidades = [];
            }
        });

        if (this.props.sku) {
            onMounted(() => {
                this.lookupSku();
                this.runPreview(null);
            });
        }

        // El SKU se consulta mientras se escribe, pero no en cada tecla.
        this._lookupTimer = null;
        onWillUnmount(() => clearTimeout(this._lookupTimer));
    }

    onSkuInput() {
        this.state.skuInfo = null;
        clearTimeout(this._lookupTimer);
        this._lookupTimer = setTimeout(() => this.lookupSku(), 500);
    }

    async lookupSku() {
        const sku = this.state.sku.trim();
        if (!sku) {
            this.state.skuInfo = null;
            return;
        }
        this.state.lookingUp = true;
        try {
            const info = await this.orm.call(MODEL, "get_sku_info", [sku]);
            this.state.skuInfo = info;
            // Coresa cotiza por su empaque: publicar por empaque deja el
            // precio exacto que compone el proveedor.
            if (info.found && info.suggestedUnits) {
                this.state.variant.units = info.suggestedUnits;
            }
        } catch (error) {
            this.state.skuInfo = null;
        } finally {
            this.state.lookingUp = false;
        }
    }

    get skuInfo() {
        return this.state.skuInfo && this.state.skuInfo.found ? this.state.skuInfo : null;
    }

    get modalidadFactor() {
        const found = this.state.modalidades.find(
            (one) => one.modalidad === this.state.variant.modalidad
        );
        return (found || {}).coeficiente || 1;
    }

    // Con el precio unitario y el coeficiente alcanza: el precio se mueve
    // con las unidades sin pedirle nada a la API.
    get estimatedPrice() {
        const info = this.skuInfo;
        if (!info || !info.unitPrice) {
            return 0;
        }
        return info.unitPrice * (Number(this.state.variant.units) || 1) * this.modalidadFactor;
    }

    get estimatedStock() {
        const info = this.skuInfo;
        const units = Number(this.state.variant.units) || 1;
        return info ? Math.floor((info.available_qty || 0) / units) : 0;
    }

    // Coresa marca que no se vende suelto: es un aviso, no un bloqueo.
    get unitSaleWarning() {
        const info = this.skuInfo;
        if (!info || info.unitSale || !info.package) {
            return "";
        }
        const units = Number(this.state.variant.units) || 1;
        if (units >= info.package) {
            return "";
        }
        return `Coresa marca este producto como no vendible por unidad y lo trae en ${this.formatUnits(
            info.package
        )}. Estás por publicarlo de a ${this.formatUnits(units)}.`;
    }

    // La combinación ya publicada da 409: mejor avisar antes de gastar el
    // preview, que llama a OpenAI.
    get duplicateVariant() {
        const info = this.skuInfo;
        const variant = this.state.variant;
        const candidates = (info && info.publishedVariants) || this.publishedVariants;
        return (
            candidates.find(
                (one) =>
                    one.listingType === variant.listingType &&
                    Number(one.units) === Number(variant.units) &&
                    one.modalidad === variant.modalidad
            ) || null
        );
    }

    // ML no ofrece las mismas cuotas en los dos tipos: el desplegable se
    // recorta en vez de dejar que la API devuelva 400.
    get availableModalidades() {
        const type = this.state.variant.listingType;
        return this.state.modalidades.filter(
            (one) => !one.listingTypes || one.listingTypes.includes(type)
        );
    }

    get modalidadHint() {
        return this.state.variant.listingType === "gold_pro"
            ? "En premium se pueden ofrecer 3, 6, 9 y 12 cuotas."
            : "En clásica solo hay contado y cuota promocionada: las cuotas son de premium.";
    }

    onListingTypeChange() {
        const allowed = this.availableModalidades.map((one) => one.modalidad);
        if (!allowed.includes(this.state.variant.modalidad)) {
            this.state.variant.modalidad = allowed.includes("contado") ? "contado" : allowed[0] || "";
        }
    }

    packageSourceLabel(source) {
        const labels = { master: "caja master", intermedia: "caja intermedia", intermediate: "caja intermedia" };
        return labels[source] || source || "";
    }

    get modalidadLabel() {
        return this.modalidadName(this.state.variant.modalidad);
    }

    get checks() {
        return (this.state.data && this.state.data.checks) || { links: [], measures: [] };
    }

    get hasIssues() {
        return Boolean(this.checks.links.length || this.checks.measures.length);
    }

    // Los dos problemas vienen armados de antes; el panel es el ultimo lugar
    // donde se pueden sacar antes de que ML los rechace (o de baja).
    async fixIssues() {
        if (this.state.fixing) {
            return;
        }
        this.state.fixing = true;
        try {
            const fixed = await this.orm.call(MODEL, "fix_draft_issues", [
                this.state.data.publicationId,
            ]);
            // La respuesta es la del editor: se mezcla para no perder la
            // variante ni la cuenta del precio, que solo trae el preview.
            Object.assign(this.state.data, {
                status: fixed.status,
                draft: Object.assign({}, this.state.data.draft, fixed.draft),
                validation: fixed.validation,
                missing: fixed.missing,
                checks: fixed.checks,
            });
        } catch (error) {
            this.state.error = error?.data?.message || "No se pudo corregir el borrador.";
        } finally {
            this.state.fixing = false;
        }
    }

    get publishedVariants() {
        return (this.state.data && this.state.data.publishedVariants) || [];
    }

    // La modalidad se guarda por clave ("12_cuotas") pero se lee por su
    // etiqueta.
    modalidadName(modalidad) {
        const found = this.state.modalidades.find((one) => one.modalidad === modalidad);
        return (found || {}).label || modalidad || "—";
    }

    variantLabel(variant) {
        const units = variant.units > 1 ? `${variant.units} unidades` : "1 unidad";
        return `${this.listingLabel(variant.listingType)} · ${units} · ${this.modalidadName(variant.modalidad)}`;
    }

    get hasResult() {
        return Boolean(this.state.data);
    }

    // El borrador vale para publicar solo si algun tipo de publicacion valida.
    get anyValid() {
        const rows = (this.state.data && this.state.data.validation) || [];
        return rows.some((row) => row.valid);
    }

    get blockingRows() {
        const rows = (this.state.data && this.state.data.validation) || [];
        return rows.filter((row) => !row.valid);
    }

    async runPreview(categoryId = null) {
        const sku = this.state.sku.trim();
        if (!sku) {
            this.state.error = "Ingresá un SKU de Coresa.";
            return;
        }
        this.state.loading = true;
        this.state.error = "";
        try {
            this.state.data = await this.orm.call(MODEL, "preview_payload", [sku], {
                category_id: categoryId,
                listing_type: this.state.variant.listingType,
                units_per_listing: this.state.variant.units,
                modalidad: this.state.variant.modalidad,
            });
            this.state.descriptionOpen = false;
        } catch (error) {
            this.state.data = null;
            this.state.error =
                error?.data?.message || "No se pudo armar el borrador para ese SKU.";
        } finally {
            this.state.loading = false;
        }
    }

    submit(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.runPreview(null);
    }

    // Cada categoria tiene sus propios atributos obligatorios: cambiarla
    // rehace el borrador entero, no es solo una etiqueta.
    useCategory(categoryId) {
        if (this.state.loading || categoryId === this.state.data.categoryId) {
            return;
        }
        this.runPreview(categoryId);
    }

    toggleDescription() {
        this.state.descriptionOpen = !this.state.descriptionOpen;
    }

    openPicture(url) {
        if (url) {
            window.open(url, "_blank", "noopener");
        }
    }

    conditionLabel(condition) {
        return CONDITIONS[condition] || condition || "—";
    }

    listingLabel(listingType) {
        return LISTING_TYPES[listingType] || listingType || "—";
    }

    shippingLabel(shipping) {
        if (!shipping || !shipping.mode) {
            return "—";
        }
        const mode = SHIPPING_MODES[shipping.mode] || shipping.mode;
        return shipping.freeShipping ? `${mode} · envío gratis` : mode;
    }

    statusLabel(status) {
        const labels = {
            draft: "Borrador",
            ready: "Listo para publicar",
            publishing: "Publicando",
            published: "Publicado",
            partial: "Parcial",
            failed: "Con error",
            discarded: "Descartado",
        };
        return labels[status] || status || "—";
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

    formatFactor(value) {
        return new Intl.NumberFormat("es-AR", {
            minimumFractionDigits: 4,
            maximumFractionDigits: 4,
        }).format(Number(value) || 1);
    }

    // El costo viene como fraccion: 0.216 es 21,6%.
    formatCost(value) {
        return new Intl.NumberFormat("es-AR", {
            style: "percent",
            maximumFractionDigits: 1,
        }).format(Number(value) || 0);
    }

    openLink(url) {
        if (url) {
            window.open(url, "_blank", "noopener");
        }
    }
}

/* ------------------------------------------------------------------ */
/* Pestaña 2: la cola, lo que todavia no se mando                      */
/* ------------------------------------------------------------------ */
class PublisherQueueTab extends Component {
    static template = "coresa_meli_publisher.PublisherQueueTab";
    static props = {
        onPreview: { type: Function, optional: true },
        onEdit: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            items: [],
            counters: {},
            total: 0,
            loading: false,
            error: "",
            // id -> true. Lo que se va a mandar a publicar.
            selected: {},
            // El envio: se hace de a uno y se ve avanzar.
            run: { active: false, cancel: false, done: 0, total: 0, current: 0, results: {} },
        });
        onWillStart(() => this.load());
    }

    get selectedIds() {
        return this.state.items
            .map((row) => row.id)
            .filter((id) => this.state.selected[id]);
    }

    get allSelected() {
        return this.state.items.length > 0 && this.selectedIds.length === this.state.items.length;
    }

    get progressPercent() {
        const run = this.state.run;
        return run.total ? Math.round((run.done / run.total) * 100) : 0;
    }

    get runSummary() {
        const results = Object.values(this.state.run.results);
        return {
            done: results.filter((one) => one.state === "done").length,
            failed: results.filter((one) => one.state === "failed").length,
        };
    }

    toggle(row) {
        if (this.state.run.active) {
            return;
        }
        this.state.selected[row.id] = !this.state.selected[row.id];
    }

    toggleAll() {
        if (this.state.run.active) {
            return;
        }
        const select = !this.allSelected;
        for (const row of this.state.items) {
            this.state.selected[row.id] = select;
        }
    }

    resultFor(row) {
        return this.state.run.results[row.id] || null;
    }

    // ------------------------------------------------------------------
    publishSelected() {
        const ids = this.selectedIds;
        if (!ids.length) {
            this.notification.add("Elegí al menos una publicación.", { type: "warning" });
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: ids.length === 1 ? "Publicar en MercadoLibre" : `Publicar ${ids.length} en MercadoLibre`,
            body:
                `Se crean ${ids.length === 1 ? "la publicación real" : `${ids.length} publicaciones reales`} ` +
                "en la cuenta de MercadoLibre, como clásicas. Van de a una y se ve el avance. " +
                "Desde el panel no se pueden deshacer: hay que entrar a MercadoLibre para pausarlas o borrarlas.",
            confirmLabel: "Publicar",
            cancelLabel: "Cancelar",
            confirm: () => this.runPublish(ids),
        });
    }

    // Se mandan de a una y se espera la respuesta: el back las procesa mejor
    // asi, y ademas cada una tarda entre 10 y 40 segundos.
    async runPublish(ids) {
        const run = this.state.run;
        Object.assign(run, { active: true, cancel: false, done: 0, total: ids.length, current: 0, results: {} });
        for (const row of this.state.items) {
            if (ids.includes(row.id)) {
                run.results[row.id] = { state: "queued", sku: row.sku, permalink: "", error: "" };
            }
        }

        for (const id of ids) {
            if (run.cancel) {
                run.results[id].state = "cancelled";
                continue;
            }
            run.current = id;
            run.results[id].state = "publishing";
            try {
                const result = await this.orm.call(MODEL, "publish_one", [id]);
                const ok = result.status === "published";
                Object.assign(run.results[id], {
                    state: ok ? "done" : "failed",
                    permalink: result.permalink || "",
                    itemId: result.itemId || "",
                    linkedForSync: Boolean(result.linkedForSync),
                    error: result.error || (ok ? "" : "MercadoLibre no la publicó."),
                });
                if (ok && !result.linkedForSync) {
                    this.notification.add(
                        `${result.sku} quedó publicada pero NO enganchada al actualizador: nadie le va a mantener precio ni stock.`,
                        { type: "warning", sticky: true }
                    );
                }
            } catch (error) {
                Object.assign(run.results[id], {
                    state: "failed",
                    error: error?.data?.message || "No se pudo publicar.",
                });
            }
            run.done += 1;
        }

        run.active = false;
        run.current = 0;
        const summary = this.runSummary;
        this.notification.add(
            summary.failed
                ? `${summary.done} publicadas, ${summary.failed} con error.`
                : `${summary.done} publicadas.`,
            { type: summary.failed ? "warning" : "success" }
        );
        // No se recarga sola: si se recargara, las publicadas desaparecen de
        // la lista (ya no estan "ready") y con ellas el link a MercadoLibre.
        this.state.selected = {};
    }

    cancelRun() {
        // Corta despues de la que esta en curso: no se puede abortar a mitad
        // de camino sin dejar la publicacion en un limbo.
        this.state.run.cancel = true;
        this.notification.add("Se corta cuando termine la que está en curso.", { type: "info" });
    }

    openLink(url) {
        if (url) {
            window.open(url, "_blank", "noopener");
        }
    }

    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "get_publisher_queue", []);
            this.state.items = result.items || [];
            const alive = new Set(this.state.items.map((row) => row.id));
            for (const id of Object.keys(this.state.selected)) {
                if (!alive.has(Number(id))) {
                    delete this.state.selected[id];
                }
            }
            this.state.counters = result.counters || {};
            this.state.total = result.total || 0;
        } catch (error) {
            this.state.items = [];
            this.state.error = error?.data?.message || "No se pudo leer la cola.";
        } finally {
            this.state.loading = false;
        }
    }

    counterFor(status) {
        return Number(this.state.counters[status]) || 0;
    }

    preview(sku) {
        if (this.props.onPreview) {
            this.props.onPreview(sku);
        }
    }

    edit(row) {
        if (this.props.onEdit) {
            this.props.onEdit(row);
        }
    }

    statusLabel(status) {
        return status === "ready" ? "Listo para publicar" : "Borrador";
    }

    resultLabel(state) {
        const labels = {
            queued: "En cola",
            publishing: "Publicando...",
            done: "Publicada",
            failed: "Con error",
            cancelled: "Cancelada",
        };
        return labels[state] || state;
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
            return String(value);
        }
        return new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(date);
    }
}

/* ------------------------------------------------------------------ */
/* Pestaña 4: dar de baja una publicación                              */
/* ------------------------------------------------------------------ */
class PublisherDeleteTab extends Component {
    static template = "coresa_meli_publisher.PublisherDeleteTab";
    static props = { onPublishAgain: { type: Function, optional: true } };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            items: [],
            counters: {},
            total: 0,
            limit: 24,
            offset: 0,
            status: "published",
            search: "",
            // La fila que se esta por eliminar y el SKU que se escribio.
            target: null,
            typed: "",
            busy: false,
            // Para el lote: que filas se eligieron y la palabra de confirmacion.
            selected: {},
            bulkOpen: false,
            bulkTyped: "",
            // El envio: de a una, igual que al publicar.
            run: { active: false, cancel: false, done: 0, total: 0, current: 0 },
            // Lo que devolvio el borrado, fila por fila.
            results: {},
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

    get confirmed() {
        const target = this.state.target;
        return Boolean(
            target && this.state.typed.trim().toUpperCase() === (target.sku || "").toUpperCase()
        );
    }

    async loadCounters() {
        try {
            this.state.counters = await this.orm.call(MODEL, "get_publication_counters", []);
        } catch (error) {
            this.state.counters = {};
        }
    }

    counterFor(status) {
        return Number(this.state.counters[status]) || 0;
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const filters = { status: this.state.status };
            if (this.state.search.trim()) {
                filters.sku = this.state.search.trim();
            }
            const result = await this.orm.call(MODEL, "get_publications_page", [], {
                limit: this.state.limit,
                offset,
                filters,
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.total = result.pagination.total || 0;
        } catch (error) {
            this.state.items = [];
            this.state.total = 0;
            this.state.error = error?.data?.message || "No se pudo leer el listado.";
        } finally {
            this.state.loading = false;
        }
    }

    setStatus(status) {
        this.state.status = status;
        this.cancel();
        this.loadPage(0);
    }

    applySearch(ev) {
        if (ev) {
            ev.preventDefault();
        }
        this.loadPage(0);
    }

    resetSearch() {
        this.state.search = "";
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
    // Lote: se eligen varias y se mandan de a una.
    // ------------------------------------------------------------------
    get selectedRows() {
        return this.state.items.filter((row) => this.state.selected[row.id]);
    }

    get allSelected() {
        return this.state.items.length > 0 && this.selectedRows.length === this.state.items.length;
    }

    get bulkConfirmed() {
        return this.state.bulkTyped.trim().toUpperCase() === "ELIMINAR";
    }

    get progressPercent() {
        const run = this.state.run;
        return run.total ? Math.round((run.done / run.total) * 100) : 0;
    }

    get runSummary() {
        const results = Object.values(this.state.results);
        return {
            done: results.filter((one) => one.listings.every((listing) => listing.deleted)).length,
            partial: results.filter((one) => one.listings.some((listing) => !listing.deleted)).length,
        };
    }

    toggle(row) {
        if (this.state.run.active) {
            return;
        }
        this.state.selected[row.id] = !this.state.selected[row.id];
    }

    toggleAll() {
        if (this.state.run.active) {
            return;
        }
        const select = !this.allSelected;
        for (const row of this.state.items) {
            this.state.selected[row.id] = select;
        }
    }

    openBulk() {
        if (!this.selectedRows.length) {
            this.notification.add("Elegí al menos una publicación.", { type: "warning" });
            return;
        }
        this.cancel();
        this.state.bulkOpen = true;
        this.state.bulkTyped = "";
    }

    closeBulk() {
        this.state.bulkOpen = false;
        this.state.bulkTyped = "";
    }

    // De a una, esperando cada respuesta: cada borrado toca MercadoLibre y
    // el actualizador, y conviene ver cual fallo.
    async runBulk() {
        if (!this.bulkConfirmed || this.state.run.active) {
            return;
        }
        const rows = this.selectedRows.slice();
        const run = this.state.run;
        Object.assign(run, { active: true, cancel: false, done: 0, total: rows.length, current: 0 });
        this.state.bulkOpen = false;
        let pendingSync = 0;
        let failed = 0;

        for (const row of rows) {
            if (run.cancel) {
                break;
            }
            run.current = row.id;
            try {
                // El SKU sale del listado, no de lo que se escribio: si la
                // lista quedo vieja y ese id ya es otro SKU, la API lo frena.
                const result = await this.orm.call(MODEL, "delete_publication", [row.id, row.sku]);
                this.state.results[row.id] = result;
                pendingSync += result.pendingSync.length ? 1 : 0;
            } catch (error) {
                failed += 1;
                this.state.results[row.id] = {
                    sku: row.sku,
                    listings: [],
                    pendingMeli: [],
                    pendingSync: [],
                    error: error?.data?.message || "No se pudo eliminar.",
                };
            }
            run.done += 1;
        }

        run.active = false;
        run.current = 0;
        this.state.selected = {};
        this.notification.add(
            failed
                ? `${run.done - failed} eliminadas, ${failed} con error.`
                : `${run.done} eliminadas.`,
            { type: failed ? "warning" : "success" }
        );
        if (pendingSync) {
            this.notification.add(
                `${pendingSync} quedaron en el actualizador: les van a seguir escribiendo precio y stock. Sacalas a mano.`,
                { type: "danger", sticky: true }
            );
        }
        await this.loadCounters();
    }

    cancelRun() {
        this.state.run.cancel = true;
        this.notification.add("Se corta cuando termine la que está en curso.", { type: "info" });
    }

    // ------------------------------------------------------------------
    pick(row) {
        this.state.target = row;
        this.state.typed = "";
    }

    cancel() {
        this.state.target = null;
        this.state.typed = "";
    }

    resultFor(row) {
        return this.state.results[row.id] || null;
    }

    async confirmDelete() {
        if (!this.confirmed || this.state.busy) {
            return;
        }
        const target = this.state.target;
        this.state.busy = true;
        try {
            const result = await this.orm.call(MODEL, "delete_publication", [
                target.id,
                this.state.typed.trim(),
            ]);
            this.state.results[target.id] = result;
            this.cancel();
            this.notification.add(`${result.sku} se eliminó de MercadoLibre.`, { type: "success" });
            // Lo que quedo a medias hay que accionarlo a mano; lo que sigue
            // en el actualizador es lo urgente.
            if (result.pendingSync.length) {
                this.notification.add(
                    `${result.sku} quedó en el actualizador: le van a seguir escribiendo precio y stock. Sacalo a mano.`,
                    { type: "danger", sticky: true }
                );
            }
            if (result.pendingMeli.length) {
                this.notification.add(
                    `MercadoLibre no cerró ${result.sku}: hay que darla de baja desde ML.`,
                    { type: "warning", sticky: true }
                );
            }
            await this.loadCounters();
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo eliminar.", {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.busy = false;
        }
    }

    publishAgain(sku) {
        if (this.props.onPublishAgain) {
            this.props.onPublishAgain(sku);
        }
    }

    openMeli(itemId) {
        if (itemId) {
            window.open(`https://articulo.mercadolibre.com.ar/${itemId}`, "_blank", "noopener");
        }
    }

    openLink(url) {
        if (url) {
            window.open(url, "_blank", "noopener");
        }
    }

    // ------------------------------------------------------------------
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

    formatDate(value) {
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

/* ------------------------------------------------------------------ */
/* El contenedor con las cuatro pestañas                                */
/* ------------------------------------------------------------------ */
class CoresaPublisherAction extends Component {
    static template = "coresa_meli_publisher.PublisherAction";
    static components = {
        PublisherPreviewTab,
        PublisherQueueTab,
        PublicationsEmbedded,
        PublisherDeleteTab,
        PublicationEditor,
    };

    setup() {
        this.state = useState({ tab: "preview", previewSku: "", editingId: 0 });
    }

    setTab(tab) {
        if (tab !== "preview") {
            this.state.previewSku = "";
        }
        this.state.tab = tab;
    }

    // Desde la cola se salta a previsualizar con el SKU ya cargado.
    openPreview(sku) {
        this.state.previewSku = sku || "";
        this.state.tab = "preview";
    }

    // El editor se come la pantalla entera: tiene su propia barra con
    // volver, guardar y publicar.
    openEditor(row) {
        this.state.editingId = Number(row && row.id) || 0;
    }

    closeEditor() {
        this.state.editingId = 0;
    }

    // Despues de eliminar, el SKU queda libre para volver a publicarlo.
    publishAgain(sku) {
        this.state.editingId = 0;
        this.state.previewSku = sku || "";
        this.state.tab = "preview";
    }
}

registry.category("actions").add("coresa_meli_publisher.publisher_action", CoresaPublisherAction);
