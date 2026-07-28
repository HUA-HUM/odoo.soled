import json

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RetailerOncityProduct(models.Model):
    _name = "retailer.oncity.product"
    _description = "OnCity Product"
    _order = "updated_at desc, publication_id desc"

    publication_id = fields.Integer(string="ID publicación", required=True, index=True)
    seller_sku = fields.Char(string="SKU vendedor", index=True)
    market_sku = fields.Char(string="SKU marketplace", index=True)
    title = fields.Char(string="Título", index=True)
    price = fields.Float(string="Precio")
    stock = fields.Integer(string="Stock")
    status = fields.Char(string="Estado", index=True)
    link_publication = fields.Char(string="Link publicación")
    thumbnail = fields.Char(string="Imagen principal")
    images_json = fields.Text(string="Imágenes JSON")
    payload_json = fields.Text(string="Payload completo JSON")
    synced_at = fields.Datetime(string="Sincronizado en")
    updated_at = fields.Datetime(string="Actualizado en")

    _sql_constraints = [
        (
            "publication_id_unique",
            "unique(publication_id)",
            "La publicación de OnCity ya existe.",
        )
    ]

    @api.model
    def _api_base_url(self):
        return "https://marketplace.api.solediluminacion.com/oncity/products/all"

    @api.model
    def _api_headers(self):
        return {"accept": "*/*"}

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
    def _to_json(self, value):
        return json.dumps(value if value is not None else [], ensure_ascii=False, indent=2)

    @api.model
    def _prepare_product_values(self, product):
        images = product.get("images") or []
        return {
            "publication_id": self._to_int(product.get("publicationId")),
            "seller_sku": product.get("sellerSku"),
            "market_sku": product.get("marketSku"),
            "title": product.get("title"),
            "price": self._to_float(product.get("price")),
            "stock": self._to_int(product.get("stock")),
            "status": product.get("status"),
            "link_publication": product.get("linkPublicacion"),
            "thumbnail": images[0] if images else False,
            "images_json": self._to_json(images),
            "payload_json": self._to_json(product),
            "synced_at": fields.Datetime.now(),
            "updated_at": fields.Datetime.now(),
        }

    def action_open_publication(self):
        self.ensure_one()
        if not self.link_publication:
            raise UserError(_("Este producto no tiene link de publicación."))
        return {
            "type": "ir.actions.act_url",
            "url": self.link_publication,
            "target": "new",
        }

    @api.model
    def _fetch_page(self, limit, offset):
        try:
            response = requests.get(
                self._api_base_url(),
                headers=self._api_headers(),
                params={"limit": limit, "offset": offset},
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando OnCity: %s") % error) from error
        except ValueError as error:
            raise UserError(_("OnCity no devolvió JSON válido.")) from error

    @api.model
    def _upsert_products(self, products):
        created_count = 0
        updated_count = 0
        skipped_count = 0
        synced_ids = []
        for product in products:
            publication_id = self._to_int(product.get("publicationId"))
            if not publication_id:
                skipped_count += 1
                continue

            values = self._prepare_product_values(product)
            existing = self.search([("publication_id", "=", publication_id)], limit=1)
            if existing:
                existing.write(values)
                updated_count += 1
            else:
                self.create(values)
                created_count += 1
            synced_ids.append(publication_id)
        return synced_ids, created_count, updated_count, skipped_count

    @api.model
    def action_sync_products(self):
        limit = 100
        offset = 0
        has_next = True
        created_count = 0
        updated_count = 0
        skipped_count = 0

        while has_next:
            payload = self._fetch_page(limit, offset)
            products = payload.get("items") or []
            _ids, created, updated, skipped = self._upsert_products(products)
            created_count += created
            updated_count += updated
            skipped_count += skipped

            has_next = bool(payload.get("hasNext"))
            offset = self._to_int(payload.get("nextOffset")) or offset + limit
            if not products and has_next:
                break

        message = _(
            "Catálogo OnCity actualizado. Creados: %(created)s. Actualizados: %(updated)s. Omitidos: %(skipped)s."
        ) % {
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
        }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("OnCity"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def get_catalog_page(self, limit=24, offset=0, search=None):
        if search:
            domain = ["|", ("seller_sku", "ilike", search), ("title", "ilike", search)]
            total = self.search_count(domain)
            records = self.search(domain, limit=limit, offset=offset)
        else:
            payload = self._fetch_page(limit, offset)
            products = payload.get("items") or []
            synced_ids, _created, _updated, _skipped = self._upsert_products(products)
            total = self.search_count([])
            records = self.search([("publication_id", "in", synced_ids)]) if synced_ids else self.browse()
        return {
            "items": [record._catalog_item() for record in records],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }

    def _catalog_item(self):
        self.ensure_one()
        return {
            "id": self.id,
            "sku": self.seller_sku,
            "external_ref": self.market_sku,
            "title": self.title,
            "price": self.price,
            "stock": self.stock,
            "status_label": self.status,
            "active": (self.status or "").lower() == "activo",
            "thumbnail": self.thumbnail,
            "link": self.link_publication,
        }
