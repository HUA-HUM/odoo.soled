/** @odoo-module **/

import { Component, onMounted, onWillStart, useState } from "@odoo/owl";
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
            data: null,
            loading: false,
            error: "",
            // La descripcion la escribe un modelo y es larga: arranca plegada.
            descriptionOpen: false,
        });

        if (this.props.sku) {
            onMounted(() => this.runPreview(null));
        }
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
        this.state = useState({
            items: [],
            counters: {},
            total: 0,
            loading: false,
            error: "",
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const result = await this.orm.call(MODEL, "get_publisher_queue", []);
            this.state.items = result.items || [];
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
/* El contenedor con las tres pestañas                                 */
/* ------------------------------------------------------------------ */
class CoresaPublisherAction extends Component {
    static template = "coresa_meli_publisher.PublisherAction";
    static components = { PublisherPreviewTab, PublisherQueueTab, PublicationsEmbedded, PublicationEditor };

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
}

registry.category("actions").add("coresa_meli_publisher.publisher_action", CoresaPublisherAction);
