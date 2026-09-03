/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

class SoledGlobalSidebar extends Component {
    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        // `trail` guarda las secciones visitadas para el boton de atras. El
        // router hace pushState, que no emite hashchange, asi que llevamos el
        // historial aca en vez de depender del historial del navegador.
        this.state = useState({ activeKey: "home", trail: [] });
        this.operationalModules = [
            {
                key: "home",
                label: "Inicio",
                description: "Panel SOLED",
                icon: "fa-home",
                action: "soled_dashboard_panel.action_soled_dashboard",
            },
            {
                key: "mercadolibre",
                label: "MercadoLibre",
                description: "Catálogo y órdenes",
                icon: "fa-handshake-o",
                action: "ml_catalog_panel.action_ml_dashboard",
            },
            {
                key: "retailers",
                label: "Retailers",
                description: "OnCity y Frávega",
                icon: "fa-shopping-bag",
                action: "retailer_marketplace_panel.action_retailer_dashboard",
            },
            {
                key: "publisher",
                label: "Publicador",
                description: "Publicación de SKU",
                icon: "fa-upload",
                action: "sku_publisher_panel.action_publisher_dashboard_panel",
            },
            {
                key: "updater",
                label: "Actualizador",
                description: "Cambios y métricas",
                icon: "fa-refresh",
                action: "retailer_marketplace_panel.action_marketplace_change_cards",
            },
            {
                key: "coresa",
                label: "Coresa",
                description: "Operaciones Coresa",
                icon: "fa-cube",
                action: "coresa_panel.action_coresa_dashboard",
            },
        ];
        this.systemModules = [
            {
                key: "administration",
                label: "Administración",
                description: "Procesos internos",
                icon: "fa-building-o",
                action: "soled_dashboard_panel.action_soled_dashboard_administration",
            },
            {
                key: "settings",
                label: "Configuración",
                description: "Usuarios y ajustes",
                icon: "fa-cog",
                action: "soled_dashboard_panel.action_soled_dashboard_configurations",
            },
        ];
        this.allModules = [...this.operationalModules, ...this.systemModules];
    }

    get previousModule() {
        const previousKey = this.state.trail[this.state.trail.length - 1];
        return previousKey ? this.allModules.find((m) => m.key === previousKey) : null;
    }

    async openModule(module, { track = true } = {}) {
        const origin = this.state.activeKey;
        if (track && origin && origin !== module.key) {
            this.state.trail.push(origin);
        }
        this.state.activeKey = module.key;
        try {
            await this.action.doAction(module.action);
        } catch (error) {
            // La seccion no se abrio: deshacemos el salto para que el boton de
            // atras y el resaltado sigan reflejando donde esta el usuario.
            this.state.activeKey = origin;
            if (track && origin && origin !== module.key) {
                this.state.trail.pop();
            }
            this.notification.add(`No se pudo abrir ${module.label}.`, { type: "danger" });
        }
    }

    async goBack() {
        const target = this.previousModule;
        if (!target) {
            return;
        }
        this.state.trail.pop();
        await this.openModule(target, { track: false });
    }
}

SoledGlobalSidebar.template = "soled_dashboard_panel.GlobalSidebar";
SoledGlobalSidebar.components = { UserMenu };

registry.category("main_components").add("soled_dashboard_panel.GlobalSidebar", {
    Component: SoledGlobalSidebar,
});
