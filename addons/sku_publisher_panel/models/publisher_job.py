from odoo import _, api, fields, models


class PublisherJob(models.Model):
    _name = "publisher.job"
    _description = "SKU Publisher Job"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    status = fields.Selection(
        [
            ("draft", "Borrador"),
            ("queued", "En cola"),
            ("processing", "Procesando"),
            ("done", "Finalizado"),
            ("error", "Error"),
        ],
        default="queued",
        required=True,
        index=True,
    )
    retailer_targets = fields.Char(string="Retailers")
    progress = fields.Integer(default=0)
    total_items = fields.Integer()
    done_items = fields.Integer()
    error_items = fields.Integer()
    backend_job_id = fields.Char(string="Job backend")
    message = fields.Text()
    line_ids = fields.One2many("publisher.job.line", "job_id", string="Lineas")

    @api.model
    def create_from_candidates(self, candidates, retailers):
        job = self.create(
            {
                "name": _("Publicacion %s") % fields.Datetime.now(),
                "retailer_targets": ", ".join(retailers),
                "total_items": len(candidates) * len(retailers),
                "message": "Pendiente de conectar endpoint backend de publicacion.",
            }
        )
        line_values = []
        for candidate in candidates:
            for retailer in retailers:
                line_values.append(
                    {
                        "job_id": job.id,
                        "sku_id": candidate.id,
                        "sku": candidate.sku,
                        "retailer": retailer,
                        "status": "queued",
                    }
                )
        self.env["publisher.job.line"].create(line_values)
        return job

    def action_refresh_progress(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Publicador"),
                "message": _("Endpoint de progreso pendiente de conectar."),
                "type": "warning",
                "sticky": False,
            },
        }


class PublisherJobLine(models.Model):
    _name = "publisher.job.line"
    _description = "SKU Publisher Job Line"
    _order = "job_id desc, id"

    job_id = fields.Many2one("publisher.job", required=True, ondelete="cascade")
    sku_id = fields.Many2one("publisher.sku", string="Candidato")
    sku = fields.Char(required=True, index=True)
    retailer = fields.Selection(
        [
            ("oncity", "OnCity"),
            ("fravega", "Fravega"),
        ],
        required=True,
        index=True,
    )
    status = fields.Selection(
        [
            ("queued", "En cola"),
            ("processing", "Procesando"),
            ("published", "Publicado"),
            ("error", "Error"),
        ],
        default="queued",
        required=True,
        index=True,
    )
    message = fields.Text()
    backend_reference = fields.Char()
