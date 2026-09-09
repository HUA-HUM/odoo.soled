from odoo import api, fields, models


class SoledDashboard(models.Model):
    _name = "soled.dashboard"
    _description = "SOLED Dashboard"

    name = fields.Char(default="Panel SOLED")

    def _open_action(self, xmlid):
        action = self.env.ref(xmlid, raise_if_not_found=False)
        if not action:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Accion no disponible",
                    "message": "Todavia no encontramos esa seccion en Odoo.",
                    "type": "warning",
                },
            }
        return action.read()[0]

    def action_open_home(self):
        return self._open_action("soled_dashboard_panel.action_soled_dashboard")

    def action_open_administration(self):
        return self._open_action("soled_dashboard_panel.action_soled_dashboard_administration")

    def action_open_commercial(self):
        return self._open_action("soled_dashboard_panel.action_soled_dashboard_commercial")

    def action_open_configurations(self):
        return self._open_action("soled_dashboard_panel.action_soled_dashboard_configurations")

    def action_open_invite_users(self):
        return self.action_open_users()

    def action_open_users(self):
        return self._open_action("base.action_res_users")

    def action_open_companies(self):
        return self._open_action("base.action_res_company_form")

    def action_open_settings(self):
        return self._open_action("base_setup.action_general_configuration")

    def action_open_ml(self):
        return self._open_action("ml_catalog_panel.action_ml_dashboard")

    def action_open_retailers(self):
        return self._open_action("retailer_marketplace_panel.action_retailer_dashboard")

    def action_open_publisher(self):
        return self._open_action("sku_publisher_panel.action_publisher_dashboard_panel")

    def action_open_coresa(self):
        return self._open_action("coresa_panel.action_coresa_dashboard")

    # ------------------------------------------------------------------
    # Navegacion global
    # ------------------------------------------------------------------
    SIDEBAR_SECTIONS = [
        {
            "key": "modules",
            "label": "Módulos",
            "items": [
                {
                    "key": "home",
                    "label": "Inicio",
                    "description": "Panel SOLED",
                    "icon": "fa-home",
                    "action": "soled_dashboard_panel.action_soled_dashboard",
                },
                {
                    "key": "mercadolibre",
                    "label": "MercadoLibre",
                    "description": "Catálogo y órdenes",
                    "icon": "fa-handshake-o",
                    "action": "ml_catalog_panel.action_ml_dashboard",
                    "children": [
                        {"key": "ml_catalog", "label": "Catálogo", "action": "ml_catalog_panel.action_ml_product"},
                        {"key": "ml_orders", "label": "Órdenes", "action": "ml_catalog_panel.action_ml_order"},
                        {"key": "ml_account", "label": "Cuenta", "action": "ml_catalog_panel.action_ml_account"},
                    ],
                },
                {
                    "key": "retailers",
                    "label": "Retailers",
                    "description": "OnCity y Frávega",
                    "icon": "fa-shopping-bag",
                    "action": "retailer_marketplace_panel.action_retailer_dashboard",
                    "children": [
                        {"key": "rt_marketplaces", "label": "Marketplaces", "action": "retailer_marketplace_panel.action_retailer_marketplace"},
                        {"key": "rt_oncity_catalog", "label": "Catálogo OnCity", "action": "retailer_marketplace_panel.action_oncity_catalog_cards"},
                        {"key": "rt_oncity_orders", "label": "Órdenes OnCity", "action": "retailer_marketplace_panel.action_oncity_order"},
                        {"key": "rt_fravega_catalog", "label": "Catálogo Frávega", "action": "retailer_marketplace_panel.action_fravega_catalog_cards"},
                        {"key": "rt_fravega_orders", "label": "Órdenes Frávega", "action": "retailer_marketplace_panel.action_fravega_order"},
                        {"key": "rt_bulk", "label": "Acciones masivas", "action": "retailer_marketplace_panel.action_retailer_bulk_actions"},
                    ],
                },
                {
                    "key": "publisher",
                    "label": "Publicador",
                    "description": "Publicación de SKU",
                    "icon": "fa-upload",
                    "action": "sku_publisher_panel.action_publisher_dashboard_panel",
                    "children": [
                        {"key": "pb_candidates", "label": "Candidatos", "action": "sku_publisher_panel.action_publisher_candidates_cards"},
                        {"key": "pb_jobs", "label": "Procesos", "action": "sku_publisher_panel.action_publisher_job"},
                        {"key": "pb_runs", "label": "Runs", "action": "sku_publisher_panel.action_publisher_run"},
                    ],
                },
                {
                    "key": "updater",
                    "label": "Actualizador",
                    "description": "Cambios y métricas",
                    "icon": "fa-refresh",
                    "action": "retailer_marketplace_panel.action_marketplace_change_cards",
                },
                {
                    "key": "coresa",
                    "label": "Coresa",
                    "description": "Operaciones Coresa",
                    "icon": "fa-cube",
                    "action": "coresa_panel.action_coresa_dashboard",
                },
            ],
        },
        {
            "key": "system",
            "label": "Sistema",
            "items": [
                {
                    "key": "administration",
                    "label": "Administración",
                    "description": "Procesos internos",
                    "icon": "fa-building-o",
                    "action": "soled_dashboard_panel.action_soled_dashboard_administration",
                },
                {
                    "key": "settings",
                    "label": "Configuración",
                    "description": "Usuarios y ajustes",
                    "icon": "fa-cog",
                    "action": "soled_dashboard_panel.action_soled_dashboard_configurations",
                },
            ],
        },
    ]

    @api.model
    def get_sidebar_sections(self):
        """Arbol del sidebar con el id numerico de cada accion.

        El front lo necesita para saber donde esta parado: Odoo escribe
        action=<id> en el hash, tanto para act_window como para acciones
        cliente. Las acciones que no existan se omiten en vez de romper la
        navegacion entera.
        """
        sections = []
        for section in self.SIDEBAR_SECTIONS:
            items = []
            for item in section["items"]:
                resolved = self._resolve_sidebar_item(item)
                if resolved:
                    items.append(resolved)
            if items:
                sections.append({"key": section["key"], "label": section["label"], "items": items})
        return sections

    @api.model
    def _resolve_sidebar_item(self, item):
        action = self.env.ref(item["action"], raise_if_not_found=False)
        if not action:
            return None
        resolved = {
            "key": item["key"],
            "label": item["label"],
            "description": item.get("description", ""),
            "icon": item.get("icon", ""),
            "action": item["action"],
            "actionId": action.id,
            "children": [],
        }
        for child in item.get("children", []):
            child_action = self.env.ref(child["action"], raise_if_not_found=False)
            if not child_action:
                continue
            resolved["children"].append(
                {
                    "key": child["key"],
                    "label": child["label"],
                    "action": child["action"],
                    "actionId": child_action.id,
                }
            )
        return resolved
