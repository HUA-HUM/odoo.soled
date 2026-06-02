from odoo import fields, models


class SoledDashboard(models.Model):
    _name = "soled.dashboard"
    _description = "SOLED Dashboard"

    name = fields.Char(default="Panel SOLED")

    def _open_action(self, xmlid):
        return self.env.ref(xmlid).read()[0]

    def action_open_ml(self):
        return self._open_action("ml_catalog_panel.action_ml_dashboard")

    def action_open_retailers(self):
        return self._open_action("retailer_marketplace_panel.action_retailer_marketplace")

    def action_open_publisher(self):
        return self._open_action("sku_publisher_panel.action_publisher_dashboard")

    def action_open_coresa(self):
        return self._open_action("coresa_panel.action_coresa_dashboard")
