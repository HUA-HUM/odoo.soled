from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoresaPublicationWizard(models.TransientModel):
    _name = "coresa.publication.wizard"
    _description = "Buscar un SKU de Coresa y armar el borrador"

    sku = fields.Char(string="SKU", required=True)

    def action_build_draft(self):
        self.ensure_one()
        # El SKU puede traer espacios y barras ("AEB 35 SC/1"): va tal cual.
        sku = self.sku or ""
        if not sku.strip():
            raise UserError(_("Ingresá un SKU."))

        publication_model = self.env["coresa.publication"]
        values = publication_model.preview_sku(sku)
        publication = publication_model._apply_values(
            publication_model.browse(), values
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Borrador de publicación"),
            "res_model": "coresa.publication",
            "res_id": publication.id,
            "view_mode": "form",
            "target": "current",
        }
