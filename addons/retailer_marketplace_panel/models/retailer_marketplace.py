from odoo import fields, models


class RetailerMarketplace(models.Model):
    _name = "retailer.marketplace"
    _description = "Retailer Marketplace"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    logo_url = fields.Char(string="Logo")
    status = fields.Selection(
        [
            ("available", "Disponible"),
            ("pending", "Pendiente"),
        ],
        default="pending",
        required=True,
    )
    description = fields.Char()
    product_count = fields.Integer(compute="_compute_product_count")
    order_count = fields.Integer(compute="_compute_section_counts")
    shipment_count = fields.Integer(compute="_compute_section_counts")
    invoice_count = fields.Integer(compute="_compute_section_counts")
    question_count = fields.Integer(compute="_compute_section_counts")

    def _compute_product_count(self):
        oncity_count = self.env["retailer.oncity.product"].search_count([])
        for marketplace in self:
            marketplace.product_count = oncity_count if marketplace.code == "oncity" else 0

    def _compute_section_counts(self):
        for marketplace in self:
            marketplace.order_count = 0
            marketplace.shipment_count = 0
            marketplace.invoice_count = 0
            marketplace.question_count = 0

    def action_open_marketplace(self):
        return self.action_open_catalog()

    def action_open_catalog(self):
        self.ensure_one()
        if self.code == "oncity":
            return self.env.ref("retailer_marketplace_panel.action_oncity_product").read()[0]
        return self._section_pending_notification("Catalogo")

    def action_open_orders(self):
        self.ensure_one()
        return self._section_pending_notification("Ordenes")

    def action_open_shipments(self):
        self.ensure_one()
        return self._section_pending_notification("Envios")

    def action_open_invoices(self):
        self.ensure_one()
        return self._section_pending_notification("Facturas")

    def action_open_questions(self):
        self.ensure_one()
        return self._section_pending_notification("Preguntas")

    def action_open_settings(self):
        self.ensure_one()
        return self._section_pending_notification("Configuracion")

    def _section_pending_notification(self, section_name):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "%s - %s" % (self.name, section_name),
                "message": "Seccion preparada. Falta conectar el endpoint correspondiente.",
                "type": "warning",
                "sticky": False,
            },
        }
