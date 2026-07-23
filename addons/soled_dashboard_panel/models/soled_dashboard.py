from odoo import fields, models


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
        return self._open_action("retailer_marketplace_panel.action_retailer_marketplace")

    def action_open_publisher(self):
        return self._open_action("sku_publisher_panel.action_publisher_dashboard")

    def action_open_coresa(self):
        return self._open_action("coresa_panel.action_coresa_dashboard")
