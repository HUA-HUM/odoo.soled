import json

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    seller_id = fields.Char(string="Seller ID", index=True)
    condition_type = fields.Char(string="Condicion")
    listing_type_id = fields.Char(string="Tipo de publicacion", index=True)
    sold_quantity = fields.Integer(string="Cantidad vendida")
    category_id = fields.Char(string="ID categoria")
    model = fields.Char(string="Modelo")
    gtin = fields.Char(string="GTIN")
    logistic_type = fields.Char(string="Tipo de logistica")
    shipping_mode = fields.Char(string="Modo de envio")
    free_shipping = fields.Boolean(string="Envio gratis")
    ml_updated_at = fields.Datetime(string="Actualizado en ML")
    description = fields.Text(string="Descripcion ML")
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
        limit = 100
        offset = 0
        total = 1
        seen_skus = set()
        created_count = 0
        updated_count = 0

        while offset < total:
            payload = self._fetch_publication_status(limit=limit, offset=offset)
            items = payload.get("items") or []
            pagination = payload.get("pagination") or {}
            total = int(pagination.get("total") or len(items) or 0)

            for item in items:
                sku = (item.get("sku") or "").strip()
                if not sku:
                    continue
                seen_skus.add(sku)
                values = self._prepare_candidate_values_from_api(item)
                existing = self.search([("sku", "=", sku)], limit=1)
                if existing:
                    existing.write(values)
                    updated_count += 1
                else:
                    self.create(values)
                    created_count += 1

            if not items:
                break
            offset += limit

        if seen_skus:
            self.search([("sku", "not in", list(seen_skus))]).unlink()

        message = _(
            "Candidatos actualizados. Creados: %(created)s. Actualizados: %(updated)s."
        ) % {"created": created_count, "updated": updated_count}
        return self._notification(message, "success")

    @api.model
    def _publication_status_base_url(self):
        return "https://internal.solediluminacion.com/internal/marketplace-publications/status-by-sku"

    @api.model
    def _fetch_publication_status(self, limit=100, offset=0, sku=None):
        params = {
            "marketplaces": "oncity,fravega",
            "limit": limit,
            "offset": offset,
        }
        if sku:
            params["sku"] = sku
        try:
            response = requests.get(
                self._publication_status_base_url(),
                headers={
                    "accept": "*/*",
                    "x-internal-api-key": "_internal",
                },
                params=params,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando candidatos del publicador: %s") % error) from error
        except ValueError as error:
            raise UserError(_("La API de candidatos no devolvio JSON valido.")) from error

    @api.model
    def _prepare_candidate_values_from_api(self, item):
        published_oncity = bool(item.get("oncity"))
        published_fravega = bool(item.get("fravega"))
        ml_status = item.get("status")
        ml_stock = self._to_int(item.get("available_quantity"))
        status = self._compute_publish_status_from_api(
            item.get("sku"),
            ml_status,
            ml_stock,
            published_oncity,
            published_fravega,
        )
        ml_product = self.env["ml.product"].search([("sku", "=", item.get("sku"))], limit=1)
        return {
            "sku": item.get("sku"),
            "title": item.get("title"),
            "brand": ml_product.brand if ml_product else False,
            "category_name": ml_product.category_name if ml_product else False,
            "ml_product_id": ml_product.id if ml_product else False,
            "meli_item_id": item.get("meli_item_id"),
            "ml_status": ml_status,
            "ml_price": self._to_float(item.get("price")),
            "ml_stock": ml_stock,
            "ml_permalink": ml_product.permalink if ml_product else False,
            "seller_id": ml_product.seller_id if ml_product else False,
            "condition_type": ml_product.condition_type if ml_product else False,
            "listing_type_id": ml_product.listing_type_id if ml_product else item.get("listing_type_id"),
            "sold_quantity": ml_product.sold_quantity if ml_product else 0,
            "category_id": ml_product.category_id if ml_product else False,
            "model": ml_product.model if ml_product else False,
            "gtin": ml_product.gtin if ml_product else False,
            "logistic_type": ml_product.logistic_type if ml_product else False,
            "shipping_mode": ml_product.shipping_mode if ml_product else False,
            "free_shipping": ml_product.free_shipping if ml_product else False,
            "ml_updated_at": ml_product.updated_at if ml_product else False,
            "description": ml_product.description if ml_product else False,
            "thumbnail": item.get("thumbnail"),
            "published_oncity": published_oncity,
            "oncity_product_id": False,
            "published_fravega": published_fravega,
            "ready_to_publish": status == "ready",
            "publish_status": status,
            "last_checked_at": fields.Datetime.now(),
            "payload_json": json.dumps(item, ensure_ascii=False, indent=2),
        }

    @api.model
    def get_candidates_page(self, limit=24, offset=0, sku=None, listing_type=None):
        listing_type = listing_type if listing_type and listing_type != "all" else None
        fetch_limit = limit
        fetch_offset = offset
        records = []
        pagination = {}
        payload = {}

        while len(records) < limit:
            payload = self._fetch_publication_status(limit=fetch_limit, offset=fetch_offset, sku=sku)
            items = payload.get("items") or []
            pagination = payload.get("pagination") or {}
            for item in items:
                values = self._prepare_candidate_values_from_api(item)
                if listing_type and not self._matches_listing_type(values.get("listing_type_id"), listing_type):
                    continue
                record = self._upsert_candidate(values)
                records.append(self._candidate_card_payload(record))
                if len(records) >= limit:
                    break
            if not items or not listing_type:
                break
            total = int(pagination.get("total") or 0)
            fetch_offset += fetch_limit
            if fetch_offset >= total:
                break

        total_count = int((pagination or {}).get("total") or len(records))
        if listing_type:
            total_count = max(offset + len(records), total_count)
        return {
            "items": records,
            "marketplaces": payload.get("marketplaces") or ["oncity", "fravega"],
            "pagination": {
                "limit": int((pagination or {}).get("limit") or limit),
                "offset": int(offset or 0),
                "total": total_count,
            },
        }

    @api.model
    def _upsert_candidate(self, values):
        existing = self.search([("sku", "=", values["sku"])], limit=1)
        if existing:
            existing.write(values)
            return existing
        return self.create(values)

    @api.model
    def _matches_listing_type(self, value, listing_type):
        normalized = value or ""
        if listing_type == "gold_clasic":
            return normalized in ("gold_clasic", "gold_classic")
        return normalized == listing_type

    @api.model
    def _candidate_card_payload(self, record):
        return {
            "id": record.id,
            "sku": record.sku,
            "meli_item_id": record.meli_item_id,
            "title": record.title,
            "status": record.ml_status,
            "price": record.ml_price,
            "stock": record.ml_stock,
            "thumbnail": record.thumbnail,
            "oncity": record.published_oncity,
            "fravega": record.published_fravega,
            "ready": record.ready_to_publish,
            "publish_status": record.publish_status,
            "brand": record.brand,
            "category_name": record.category_name,
            "category_id": record.category_id,
            "seller_id": record.seller_id,
            "condition_type": record.condition_type,
            "listing_type_id": record.listing_type_id,
            "sold_quantity": record.sold_quantity,
            "model": record.model,
            "gtin": record.gtin,
            "logistic_type": record.logistic_type,
            "shipping_mode": record.shipping_mode,
            "free_shipping": record.free_shipping,
            "permalink": record.ml_permalink,
            "description": record.description,
            "updated_at": fields.Datetime.to_string(record.ml_updated_at) if record.ml_updated_at else False,
            "payload_json": record.payload_json,
        }

    @api.model
    def publish_skus(self, skus, marketplaces):
        skus = [sku for sku in (skus or []) if sku]
        marketplaces = [marketplace for marketplace in (marketplaces or []) if marketplace]
        if not skus:
            raise UserError(_("Selecciona al menos un SKU."))
        if not marketplaces:
            raise UserError(_("Selecciona al menos un marketplace."))

        candidates = self.search([("sku", "in", skus)])
        missing_skus = sorted(set(skus) - set(candidates.mapped("sku")))
        for sku in missing_skus:
            payload = self._fetch_publication_status(limit=50, offset=0, sku=sku)
            for item in payload.get("items") or []:
                values = self._prepare_candidate_values_from_api(item)
                existing = self.search([("sku", "=", values["sku"])], limit=1)
                if existing:
                    existing.write(values)
                else:
                    self.create(values)
        candidates = self.search([("sku", "in", skus)])
        job = self.env["publisher.job"].create_from_candidates(candidates, marketplaces)
        return {
            "type": "ir.actions.act_window",
            "name": _("Proceso de publicacion"),
            "res_model": "publisher.job",
            "res_id": job.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    @api.model
    def _to_float(self, value):
        if value in (None, ""):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _to_int(self, value):
        if value in (None, ""):
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @api.model
    def _compute_publish_status_from_api(self, sku, ml_status, ml_stock, published_oncity, published_fravega):
        if not sku:
            return "missing_sku"
        if ml_status and ml_status != "active":
            return "inactive"
        if ml_stock <= 0:
            return "no_stock"
        if published_oncity and published_fravega:
            return "already_published"
        return "ready"

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
            "views": [(False, "form")],
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
