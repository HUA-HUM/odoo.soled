from odoo import _, fields, models
from odoo.exceptions import UserError


class PublisherSkuSearchWizard(models.TransientModel):
    _name = "publisher.sku.search.wizard"
    _description = "Buscar SKU para publicador"

    sku = fields.Char(string="SKU", required=True)

    def action_search_sku(self):
        self.ensure_one()
        sku = (self.sku or "").strip()
        if not sku:
            raise UserError(_("Ingresa un SKU."))

        sku_model = self.env["publisher.sku"]
        payload = sku_model._fetch_publication_status(limit=50, offset=0, sku=sku)
        items = payload.get("items") or []
        for item in items:
            values = sku_model._prepare_candidate_values_from_api(item)
            existing = sku_model.search([("sku", "=", values["sku"])], limit=1)
            if existing:
                existing.write(values)
            else:
                sku_model.create(values)

        return {
            "type": "ir.actions.act_window",
            "name": _("Resultado SKU"),
            "res_model": "publisher.sku",
            "view_mode": "tree,form",
            "domain": [("sku", "ilike", sku)],
            "target": "current",
        }
