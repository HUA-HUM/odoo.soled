/** @odoo-module **/

import { Component, onMounted, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "coresa.dashboard";

class CoresaDashboardAction extends Component {
    static template = "coresa_panel.DashboardAction";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            data: {
                catalog: 0,
                publications: 0,
                skus: 0,
                stock: 0,
                price: 0,
                publisher: { total: 0, pending: 0, published: 0, failed: 0 },
                metrics: {},
                errors: [],
            },
            sections: [],
            loading: true,
        });

        // Las tarjetas no dependen de la API: entran de una.
        onWillStart(async () => {
            this.state.sections = await this.orm.call(MODEL, "get_dashboard_sections", []);
        });
        // Los contadores leen cuatro endpoints y tardan un par de segundos:
        // llegan despues, sin dejar la pantalla en blanco mientras tanto.
        onMounted(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(MODEL, "get_dashboard_counters", []);
        } catch (error) {
            this.state.data.errors = [
                error?.data?.message || "No se pudieron leer los datos de Coresa.",
            ];
        } finally {
            this.state.loading = false;
        }
    }

    openSection(section) {
        if (!section.available) {
            return;
        }
        this.action.doAction(section.action);
    }

    formatUnits(value) {
        return new Intl.NumberFormat("es-AR").format(Number(value) || 0);
    }

    // Mientras carga, un guion en vez de un cero que no es cierto.
    num(value) {
        return this.state.loading ? "—" : this.formatUnits(value);
    }

    // Cuantas de las publicaciones registradas no sincronizan nada: es el
    // numero que suele sorprender al mirar la portada.
    get idlePublications() {
        const data = this.state.data;
        const synced = Math.max(Number(data.stock) || 0, Number(data.price) || 0);
        return Math.max(0, (Number(data.publications) || 0) - synced);
    }
}

registry.category("actions").add("coresa_panel.dashboard_action", CoresaDashboardAction);
