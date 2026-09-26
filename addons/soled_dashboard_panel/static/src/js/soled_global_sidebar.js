/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

// Odoo escribe action=<id> en el hash pero navega con pushState, que no emite
// hashchange. Miramos el hash: es la unica fuente de verdad de "donde estoy"
// que no depende de internals del action manager.
const HASH_POLL_MS = 400;

// La pestaña decia "Odoo - <lo que sea>". Odoo compone el titulo por partes
// y "zopenerp" es la que trae su marca.
const TITLE_PART = "zopenerp";
const PANEL_TITLE = "SOLED Panel";

// Iconos propios, en trazo y sobre una grilla de 24x24. FontAwesome 4 es
// solido y pesado: al lado del texto fino del sidebar quedaba sucio. Se
// mapean por key del item, con un fallback para lo que se agregue despues.
const ICON_PATHS = {
    home: [
        "M3.6 10.6 12 4l8.4 6.6",
        "M5.4 9.6V19a2 2 0 0 0 2 2h9.2a2 2 0 0 0 2-2V9.6",
        "M9.6 21v-6.2h4.8V21",
    ],
    mercadolibre: [
        "M12.9 3.2H20a.8.8 0 0 1 .8.8v7.1a2 2 0 0 1-.6 1.4l-7.7 7.7a1.8 1.8 0 0 1-2.5 0l-6.2-6.2a1.8 1.8 0 0 1 0-2.5l7.7-7.7a2 2 0 0 1 1.4-.6z",
        "M16.6 7.4h.01",
    ],
    retailers: [
        "M5.6 8.4h12.8l.9 11.1a1.5 1.5 0 0 1-1.5 1.6H6.2a1.5 1.5 0 0 1-1.5-1.6z",
        "M9 10.4V7.2a3 3 0 0 1 6 0v3.2",
    ],
    publisher: [
        "M12 15.4V3.8",
        "m7.8 8 4.2-4.2L16.2 8",
        "M4.4 15v3.6a2 2 0 0 0 2 2h11.2a2 2 0 0 0 2-2V15",
    ],
    updater: [
        "M20 12a8 8 0 1 1-2.7-6L20 8.4",
        "M20 4v4.4h-4.4",
    ],
    coresa: [
        "m12 3.4 8 4.4v8.4l-8 4.4-8-4.4V7.8z",
        "m4.2 7.9 7.8 4.3 7.8-4.3",
        "M12 12.2v8.4",
    ],
    administration: [
        "M4.6 21V5.4a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2V21",
        "M15.6 10.4h3a2 2 0 0 1 2 2V21",
        "M3 21h18",
        "M8 7.6h2.6M8 11.6h2.6M8 15.6h2.6",
    ],
    settings: [
        "M4 7h3.4M11.6 7H20M4 12h9.4M17.6 12H20M4 17h5.4M13.6 17H20",
        "M11.6 7a2.1 2.1 0 1 1-4.2 0 2.1 2.1 0 0 1 4.2 0",
        "M17.6 12a2.1 2.1 0 1 1-4.2 0 2.1 2.1 0 0 1 4.2 0",
        "M13.6 17a2.1 2.1 0 1 1-4.2 0 2.1 2.1 0 0 1 4.2 0",
    ],
};

const FALLBACK_ICON = ["M4.2 4.2h6v6h-6zM13.8 4.2h6v6h-6zM4.2 13.8h6v6h-6zM13.8 13.8h6v6h-6z"];

// Los glifos chicos de la interfaz, con el mismo trazo que los iconos.
const GLYPHS = {
    back: ["M19 12H5", "m11 18-6-6 6-6"],
    chevronDown: ["m6 9.5 6 6 6-6"],
    chevronUp: ["m18 14.5-6-6-6 6"],
    collapse: ["m13 18-6-6 6-6", "m19 18-6-6 6-6"],
    expand: ["m11 6 6 6-6 6", "m5 6 6 6-6 6"],
};

// Modo compacto: se recuerda entre recargas.
const COLLAPSED_KEY = "soled_sidebar_collapsed";

class SoledGlobalSidebar extends Component {
    static template = "soled_dashboard_panel.GlobalSidebar";
    static components = { UserMenu };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            sections: [],
            activeKey: "",
            activeChildKey: "",
            expanded: {},
            trail: [],
            collapsed: this.readCollapsed(),
            loading: true,
        });

        this.applyPanelTitle();

        onWillStart(async () => {
            try {
                this.state.sections = await this.orm.call(
                    "soled.dashboard",
                    "get_sidebar_sections",
                    []
                );
            } catch (error) {
                this.state.sections = [];
            } finally {
                this.state.loading = false;
                this.syncFromUrl();
            }
        });

        this.onHashChange = () => this.syncFromUrl();
        window.addEventListener("hashchange", this.onHashChange);
        this.lastHash = "";
        this.poller = window.setInterval(() => {
            if (window.location.hash !== this.lastHash) {
                this.syncFromUrl();
            }
        }, HASH_POLL_MS);

        onWillUnmount(() => {
            window.removeEventListener("hashchange", this.onHashChange);
            window.clearInterval(this.poller);
        });
    }

    // ------------------------------------------------------------------
    // Marca del panel
    // ------------------------------------------------------------------
    applyPanelTitle() {
        // Defensivo: si el servicio cambia de forma, la navegacion no se cae
        // por un titulo.
        try {
            const title = this.env.services.title;
            if (title && typeof title.setParts === "function") {
                title.setParts({ [TITLE_PART]: PANEL_TITLE });
            }
        } catch (error) {
            // Sin titulo propio el panel funciona igual.
        }
    }

    // ------------------------------------------------------------------
    // Iconografia
    // ------------------------------------------------------------------
    iconPaths(item) {
        return ICON_PATHS[item.key] || FALLBACK_ICON;
    }

    glyph(name) {
        return GLYPHS[name] || [];
    }

    readCollapsed() {
        try {
            return window.localStorage.getItem(COLLAPSED_KEY) === "1";
        } catch (error) {
            return false;
        }
    }

    toggleCollapsed() {
        this.state.collapsed = !this.state.collapsed;
        try {
            window.localStorage.setItem(COLLAPSED_KEY, this.state.collapsed ? "1" : "0");
        } catch (error) {
            // Sin persistencia igual funciona en esta sesion.
        }
    }

    get allItems() {
        return this.state.sections.flatMap((section) => section.items || []);
    }

    // ------------------------------------------------------------------
    // Ubicacion actual
    // ------------------------------------------------------------------
    currentActionId() {
        const match = /(?:^|[#&])action=(\d+)/.exec(window.location.hash || "");
        return match ? Number(match[1]) : null;
    }

    syncFromUrl() {
        this.lastHash = window.location.hash;
        const actionId = this.currentActionId();
        if (!actionId) {
            return;
        }
        for (const item of this.allItems) {
            if (item.actionId === actionId) {
                this.setActive(item.key, "");
                return;
            }
            const child = (item.children || []).find((entry) => entry.actionId === actionId);
            if (child) {
                this.setActive(item.key, child.key);
                return;
            }
        }
    }

    setActive(key, childKey) {
        if (this.state.activeKey !== key) {
            if (this.state.activeKey) {
                this.state.trail.push(this.state.activeKey);
            }
            this.state.activeKey = key;
        }
        this.state.activeChildKey = childKey;
        if (childKey) {
            this.state.expanded[key] = true;
        }
    }

    get previousItem() {
        const previousKey = this.state.trail[this.state.trail.length - 1];
        return previousKey ? this.allItems.find((item) => item.key === previousKey) : null;
    }

    // ------------------------------------------------------------------
    // Navegacion
    // ------------------------------------------------------------------
    isExpanded(item) {
        return Boolean(this.state.expanded[item.key]);
    }

    hasChildren(item) {
        return Boolean((item.children || []).length);
    }

    toggle(item, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        this.state.expanded[item.key] = !this.state.expanded[item.key];
    }

    async openItem(item, child = null) {
        const target = child || item;
        try {
            await this.action.doAction(target.action);
            this.setActive(item.key, child ? child.key : "");
        } catch (error) {
            // Sin el detalle, el cartel dice "no se pudo abrir" y esconde la
            // causa real, que es lo unico util para diagnosticar.
            const detail = error?.data?.message || error?.message || "";
            this.notification.add(
                detail
                    ? `No se pudo abrir ${target.label}: ${detail}`
                    : `No se pudo abrir ${target.label}.`,
                { type: "danger" }
            );
        }
    }

    async goBack() {
        const target = this.previousItem;
        if (!target) {
            return;
        }
        this.state.trail.pop();
        await this.action.doAction(target.action);
        this.state.activeKey = target.key;
        this.state.activeChildKey = "";
    }
}

registry.category("main_components").add("soled_dashboard_panel.GlobalSidebar", {
    Component: SoledGlobalSidebar,
});
