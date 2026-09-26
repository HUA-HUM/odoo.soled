from odoo import fields, models


class CoresaDashboard(models.Model):
    _name = "coresa.dashboard"
    _description = "Coresa Dashboard"

    name = fields.Char(default="Coresa")

    def action_open_catalog(self):
        action = self.env.ref("coresa_panel.action_coresa_catalog", raise_if_not_found=False)
        return action.read()[0] if action else False
