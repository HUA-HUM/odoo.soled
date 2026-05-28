import json

from odoo import _, api, fields, models


class PublisherSku(models.Model):
    _name = "publisher.sku"
    _description = "SKU Publisher Candidate"
    _order = "ready_to_publish desc, ml_stock desc, sku"

    sku = fields.Char(required=True, index=True)
    title = fields.Char(index=True)
    brand = fields.Char(index=True)
    category_name = fields.Char(string="Categoria", index=True)
    ml_product_id = fields.Many2one("ml.product", string="Producto MercadoLibre", ondelete="cascade")
    meli_item_id = fields.Char(string="ID MercadoLibre", index=True)
    ml_status = fields.Char(string="Estado ML", index=True)
    ml_price = fields.Float(string="Precio ML")
    ml_stock = fields.Integer(string="Stock ML")
    ml_permalink = fields.Char(string="Link ML")
    thumbnail = fields.Char(string="Imagen")
    published_oncity = fields.Boolean(string="Publicado OnCity", index=True)
    oncity_product_id = fields.Many2one("retailer.oncity.product", string="Producto OnCity")
    published_fravega = fields.Boolean(string="Publicado Fravega", index=True)
    ready_to_publish = fields.Boolean(string="Listo para publicar", index=True)
    publish_status = fields.Selection(
        [
            ("ready", "Listo"),
            ("already_published", "Ya publicado"),
            ("no_stock", "Sin stock"),
            ("inactive", "Inactivo"),
            ("missing_sku", "Sin SKU"),
        ],
        default="ready",
        required=True,
        index=True,
    )
    last_checked_at = fields.Datetime(string="Ultimo calculo")
    payload_json = fields.Text(string="Payload ML JSON")

    _sql_constraints = [
        ("sku_unique", "unique(sku)", "El SKU ya existe en el publicador."),
    ]

    @api.model
    def action_refresh_candidates(self):
        ml_products = self.env["ml.product"].search([])
        oncity_products = self.env["retailer.oncity.product"].search([])
        oncity_by_sku = {
            product.seller_sku.strip(): product
            for product in oncity_products
            if product.seller_sku and product.seller_sku.strip()
        }
        seen_skus = set()
        created_count = 0
        updated_count = 0

        for ml_product in ml_products:
            sku = (ml_product.sku or "").strip()
            if not sku:
                continue
            seen_skus.add(sku)
            oncity_product = oncity_by_sku.get(sku)
            values = self._prepare_candidate_values(ml_product, oncity_product)
            existing = self.search([("sku", "=", sku)], limit=1)
            if existing:
                existing.write(values)
                updated_count += 1
            else:
                self.create(values)
                created_count += 1

        if seen_skus:
            self.search([("sku", "not in", list(seen_skus))]).unlink()

        message = _(
            "Candidatos actualizados. Creados: %(created)s. Actualizados: %(updated)s."
        ) % {"created": created_count, "updated": updated_count}
        return self._notification(message, "success")

    @api.model
    def _prepare_candidate_values(self, ml_product, oncity_product):
        published_oncity = bool(oncity_product)
        published_fravega = False
        status = self._compute_publish_status(ml_product, published_oncity, published_fravega)
        return {
            "sku": ml_product.sku.strip(),
            "title": ml_product.title,
            "brand": ml_product.brand,
            "category_name": ml_product.category_name,
            "ml_product_id": ml_product.id,
            "meli_item_id": ml_product.meli_item_id,
            "ml_status": ml_product.status,
            "ml_price": ml_product.price,
            "ml_stock": ml_product.available_quantity,
            "ml_permalink": ml_product.permalink,
            "thumbnail": ml_product.thumbnail,
            "published_oncity": published_oncity,
            "oncity_product_id": oncity_product.id if oncity_product else False,
            "published_fravega": published_fravega,
            "ready_to_publish": status == "ready",
            "publish_status": status,
            "last_checked_at": fields.Datetime.now(),
            "payload_json": ml_product.payload_json or json.dumps({"id": ml_product.meli_item_id}, ensure_ascii=False),
        }

    @api.model
    def _compute_publish_status(self, ml_product, published_oncity, published_fravega):
        if not ml_product.sku:
            return "missing_sku"
        if ml_product.status and ml_product.status != "active":
            return "inactive"
        if ml_product.available_quantity <= 0:
            return "no_stock"
        if published_oncity and published_fravega:
            return "already_published"
        return "ready"

    def action_open_ml_product(self):
        self.ensure_one()
        if self.ml_product_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("Producto MercadoLibre"),
                "res_model": "ml.product",
                "res_id": self.ml_product_id.id,
                "view_mode": "form",
                "target": "current",
            }
        if self.ml_permalink:
            return {"type": "ir.actions.act_url", "url": self.ml_permalink, "target": "new"}
        return self._notification(_("Este SKU no tiene producto MercadoLibre asociado."), "warning")

    def action_publish_oncity(self):
        return self._create_publish_job(["oncity"])

    def action_publish_fravega(self):
        return self._create_publish_job(["fravega"])

    def action_publish_both(self):
        return self._create_publish_job(["oncity", "fravega"])

    def _create_publish_job(self, retailers):
        candidates = self.filtered(lambda item: item.ready_to_publish)
        if not candidates:
            return self._notification(_("Selecciona SKUs listos para publicar."), "warning")
        job = self.env["publisher.job"].create_from_candidates(candidates, retailers)
        return {
            "type": "ir.actions.act_window",
            "name": _("Proceso de publicacion"),
            "res_model": "publisher.job",
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }

    def _notification(self, message, notification_type):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Publicador"),
                "message": message,
                "type": notification_type,
                "sticky": False,
            },
        }
