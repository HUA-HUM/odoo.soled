/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";

const MODEL = "coresa.publication";

// MercadoLibre corta el titulo en 60.
const TITLE_MAX = 60;

const STATUS_TONE = {
    draft: "is-gray",
    ready: "is-green",
    publishing: "is-blue",
    published: "is-green",
    partial: "is-amber",
    failed: "is-red",
    discarded: "is-muted",
};

/** Editor de un borrador: corrige, revalida contra ML y publica. */
export class PublicationEditor extends Component {
    static template = "coresa_meli_publisher.PublicationEditor";
    static props = {
        publicationId: { type: Number },
        onClose: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            data: null,
            form: this.emptyForm(),
            newAttribute: { id: "", value: "" },
            loading: true,
            busy: "",
            error: "",
            dirty: false,
        });

        onWillStart(() => this.load());
    }

    emptyForm() {
        return {
            title: "",
            description: "",
            price: 0,
            quantity: 0,
            categoryId: "",
            attributes: [],
        };
    }

    get titleMax() {
        return TITLE_MAX;
    }

    get titleLength() {
        return (this.state.form.title || "").length;
    }

    get titleTooLong() {
        return this.titleLength > TITLE_MAX;
    }

    get statusTone() {
        return STATUS_TONE[(this.state.data || {}).status] || "is-gray";
    }

    get canPublish() {
        // El estado lo decide ML en cada revalidacion: no se hereda del
        // render anterior ni se deduce de los faltantes.
        return Boolean(this.state.data && this.state.data.canPublish) && !this.state.dirty;
    }

    // ------------------------------------------------------------------
    applyData(data) {
        this.state.data = data;
        this.state.form = {
            title: data.draft.title,
            description: data.draft.description,
            price: data.draft.price,
            quantity: data.draft.quantity,
            categoryId: data.categoryId,
            attributes: data.draft.attributes.map((attribute) => ({ ...attribute })),
        };
        this.state.dirty = false;
        this.state.newAttribute = { id: "", value: "" };
    }

    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            this.applyData(await this.orm.call(MODEL, "get_publication", [this.props.publicationId]));
        } catch (error) {
            this.state.data = null;
            this.state.error = error?.data?.message || "No se pudo abrir la publicación.";
        } finally {
            this.state.loading = false;
        }
    }

    touch() {
        this.state.dirty = true;
    }

    editAttribute(attribute) {
        // Editado a mano: el value_id de ML ya no corresponde.
        attribute.dirty = true;
        this.touch();
    }

    removeAttribute(index) {
        this.state.form.attributes.splice(index, 1);
        this.touch();
    }

    addAttribute() {
        const id = this.state.newAttribute.id.trim().toUpperCase();
        const value = this.state.newAttribute.value.trim();
        if (!id || !value) {
            this.notification.add("Poné el id del atributo y su valor.", { type: "warning" });
            return;
        }
        const existing = this.state.form.attributes.find((one) => one.id === id);
        if (existing) {
            existing.value = value;
            existing.dirty = true;
        } else {
            this.state.form.attributes.push({ id, value, valueId: "", inferred: false, dirty: true });
        }
        this.state.newAttribute = { id: "", value: "" };
        this.touch();
    }

    fillMissing(attributeId) {
        this.state.newAttribute = { id: attributeId, value: "" };
    }

    useCategory(categoryId) {
        if (categoryId === this.state.form.categoryId) {
            return;
        }
        this.state.form.categoryId = categoryId;
        this.touch();
        this.notification.add(
            "Cambiaste la categoría: revalidá para que MercadoLibre recalcule los atributos obligatorios.",
            { type: "info" }
        );
    }

    get checks() {
        return (this.state.data && this.state.data.checks) || { links: [], measures: [] };
    }

    get hasIssues() {
        return Boolean(this.checks.links.length || this.checks.measures.length);
    }

    // Saca el link del proveedor y pasa las medidas a enteros en cm y g.
    // Son los dos motivos por los que ML venia rechazando borradores.
    async fixIssues() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = "fix";
        try {
            const fixed = await this.orm.call(MODEL, "fix_draft_issues", [this.props.publicationId]);
            this.applyData(fixed);
            this.notification.add(
                fixed.canPublish
                    ? "Corregido. MercadoLibre ahora lo acepta."
                    : "Corregido, pero MercadoLibre sigue rechazando algo. Mirá el detalle.",
                { type: fixed.canPublish ? "success" : "warning" }
            );
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo corregir.", {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.busy = "";
        }
    }

    // ------------------------------------------------------------------
    async revalidate() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = "save";
        try {
            const data = await this.orm.call(MODEL, "save_draft", [
                this.props.publicationId,
                { ...this.state.form, attributes: this.state.form.attributes },
            ]);
            this.applyData(data);
            this.notification.add(
                data.canPublish
                    ? "Guardado. MercadoLibre lo acepta: se puede publicar."
                    : "Guardado, pero MercadoLibre todavía lo rechaza. Mirá el detalle.",
                { type: data.canPublish ? "success" : "warning" }
            );
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo guardar.", {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.busy = "";
        }
    }

    publish() {
        const data = this.state.data;
        this.dialog.add(ConfirmationDialog, {
            title: "Publicar en MercadoLibre",
            body:
                `Se crea la publicación real de ${data.sku} en la cuenta de MercadoLibre, ` +
                "como clásica. Desde el panel no se puede deshacer: hay que entrar a MercadoLibre para pausarla o borrarla.",
            confirmLabel: "Publicar",
            cancelLabel: "Cancelar",
            confirm: () => this.doPublish(),
        });
    }

    async doPublish() {
        this.state.busy = "publish";
        try {
            const data = await this.orm.call(MODEL, "publish_draft", [this.props.publicationId]);
            this.applyData(data);
            this.notification.add("Publicado en MercadoLibre.", { type: "success" });
            if (!data.linkedForSync) {
                // Se creo igual, pero nadie le va a mantener precio ni stock.
                this.notification.add(
                    "Quedó publicada pero NO enganchada al actualizador: nadie le va a mantener precio ni stock.",
                    { type: "warning", sticky: true }
                );
            }
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo publicar.", {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.busy = "";
        }
    }

    rebuild() {
        this.dialog.add(ConfirmationDialog, {
            title: "Volver a armar el borrador",
            body:
                "Se rehace con la IA desde los datos de Coresa. Todo lo que hayas corregido a mano " +
                "en esta pantalla se pierde.",
            confirmLabel: "Rearmar",
            cancelLabel: "Cancelar",
            confirm: () => this.doRebuild(),
        });
    }

    async doRebuild() {
        this.state.busy = "rebuild";
        try {
            const data = await this.orm.call(MODEL, "rebuild_draft", [this.state.data.sku], {
                category_id: this.state.form.categoryId || null,
            });
            this.applyData(data);
            this.notification.add("Borrador rearmado.", { type: "success" });
        } catch (error) {
            this.notification.add(error?.data?.message || "No se pudo rearmar el borrador.", {
                type: "danger",
                sticky: true,
            });
        } finally {
            this.state.busy = "";
        }
    }

    close() {
        if (this.props.onClose) {
            this.props.onClose();
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
        if (!Number.isFinite(numeric)) {
            return "—";
        }
        return new Intl.NumberFormat("es-AR", {
            style: "currency",
            currency: "ARS",
            maximumFractionDigits: 0,
        }).format(numeric);
    }

    formatDateTime(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        // Las fechas vienen en UTC: se muestran en hora local.
        return new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(date);
    }
}
