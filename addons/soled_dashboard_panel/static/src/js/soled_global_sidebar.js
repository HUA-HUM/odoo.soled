/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class SoledGlobalSidebar extends Component {
    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ activeKey: "" });
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
                action: "sku_publisher_panel.action_publisher_dashboard",
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
    }

    async openModule(module) {
        this.state.activeKey = module.key;
        try {
            await this.action.doAction(module.action);
        } catch (error) {
            this.notification.add(`No se pudo abrir ${module.label}.`, { type: "danger" });
        }
    }
}

SoledGlobalSidebar.template = "soled_dashboard_panel.GlobalSidebar";

registry.category("main_components").add("soled_dashboard_panel.GlobalSidebar", {
    Component: SoledGlobalSidebar,
});
