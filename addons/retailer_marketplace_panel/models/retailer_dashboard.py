from odoo import fields, models


class RetailerDashboard(models.Model):
    _name = "retailer.dashboard"
    _description = "Retailers Dashboard"

    name = fields.Char(default="Retailers")

    def _open_action(self, xmlid):
        action = self.env.ref(xmlid, raise_if_not_found=False)
        if action:
            return action.read()[0]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sección no disponible",
                "message": "Todavía no encontramos esa acción en Odoo.",
                "type": "warning",
                "sticky": False,
            },
        }

    def action_open_marketplaces(self):
        return self._open_action("retailer_marketplace_panel.action_retailer_marketplace")

    def action_open_publisher(self):
        return self._open_action("sku_publisher_panel.action_publisher_dashboard")

    def action_open_updater(self):
        return self._open_action("retailer_marketplace_panel.action_marketplace_change_cards")
