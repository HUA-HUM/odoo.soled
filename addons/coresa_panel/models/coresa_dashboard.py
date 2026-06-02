from odoo import fields, models


class CoresaDashboard(models.Model):
    _name = "coresa.dashboard"
    _description = "Coresa Dashboard"

    name = fields.Char(default="Coresa")
