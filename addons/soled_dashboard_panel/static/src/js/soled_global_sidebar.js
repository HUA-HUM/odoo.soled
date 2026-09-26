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
