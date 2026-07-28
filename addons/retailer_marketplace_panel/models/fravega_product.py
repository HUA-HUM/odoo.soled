import json

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RetailerFravegaProduct(models.Model):
    _name = "retailer.fravega.product"
    _description = "Fravega Product"
    _order = "synced_at desc, sku"

    external_id = fields.Char(string="ID externo", index=True)
    sku = fields.Char(string="SKU Fravega", required=True, index=True)
    ref_id = fields.Char(string="SKU SOLED", index=True)
    ean = fields.Char(string="EAN")
    title = fields.Char(string="Título", index=True)
    active = fields.Boolean(string="Activo")
    status_code = fields.Char(string="Código estado", index=True)
    status_message = fields.Char(string="Mensaje estado")
    item_state = fields.Char(string="Estado item")
    brand_id = fields.Char(string="Marca ID")
    category_id = fields.Char(string="Categoría ID")
    stock = fields.Integer(string="Stock")
    price_list = fields.Float(string="Precio lista")
    price_sale = fields.Float(string="Precio venta")
    price_net = fields.Float(string="Precio neto")
    thumbnail = fields.Char(string="Imagen principal")
    images_json = fields.Text(string="Imágenes JSON")
    attributes_json = fields.Text(string="Atributos JSON")
    required_attributes_json = fields.Text(string="Atributos requeridos JSON")
    payload_json = fields.Text(string="Payload completo JSON")
    synced_at = fields.Datetime(string="Sincronizado en")

    _sql_constraints = [
        ("fravega_sku_unique", "unique(sku)", "El SKU de Fravega ya existe."),
    ]

    @api.model
    def _api_base_url(self):
        return "https://marketplace.api.solediluminacion.com/fravega/products"

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
    def _image_url(self, name):
        if not name:
            return False
        if name.startswith("http"):
            return name
        return "https://images.fravega.com/f300/%s.webp" % name

    @api.model
    def _prepare_product_values(self, product):
        images = product.get("images") or []
        price = product.get("price") or {}
        stock = product.get("stock") or {}
        status = product.get("status") or {}
        return {
            "external_id": product.get("id"),
            "sku": product.get("sku"),
            "ref_id": product.get("refId"),
            "ean": product.get("ean"),
            "title": product.get("title"),
            "active": bool(product.get("active")),
            "status_code": status.get("code"),
            "status_message": status.get("message"),
            "item_state": product.get("itemState"),
            "brand_id": product.get("brandId"),
            "category_id": product.get("primaryCategoryId"),
            "stock": self._to_int(stock.get("quantity")),
            "price_list": self._to_float(price.get("list")),
            "price_sale": self._to_float(price.get("sale")),
            "price_net": self._to_float(price.get("net")),
            "thumbnail": self._image_url(images[0]) if images else False,
            "images_json": self._to_json(images),
            "attributes_json": self._to_json(product.get("attributes")),
            "required_attributes_json": self._to_json(product.get("requiredAttributes")),
            "payload_json": self._to_json(product),
            "synced_at": fields.Datetime.now(),
        }

    @api.model
    def _fetch_page(self, limit, offset):
        try:
            response = requests.get(
                self._api_base_url(),
                headers={"accept": "*/*"},
                params={"limit": limit, "offset": offset},
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando Fravega: %s") % error) from error
        except ValueError as error:
            raise UserError(_("Fravega no devolvió JSON válido.")) from error

    @api.model
    def _upsert_products(self, products):
        created_count = 0
        updated_count = 0
        skipped_count = 0
        synced_skus = []
        for product in products:
            sku = product.get("sku")
            if not sku:
                skipped_count += 1
                continue
            values = self._prepare_product_values(product)
            existing = self.search([("sku", "=", sku)], limit=1)
            if existing:
                existing.write(values)
                updated_count += 1
            else:
                self.create(values)
                created_count += 1
            synced_skus.append(sku)
        return synced_skus, created_count, updated_count, skipped_count

    @api.model
    def action_sync_products(self):
        limit = 100
        offset = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0

        while True:
            payload = self._fetch_page(limit, offset)
            products = payload.get("data") or []
            _skus, created, updated, skipped = self._upsert_products(products)
            created_count += created
            updated_count += updated
            skipped_count += skipped

            total = self._to_int(payload.get("total"))
            offset += limit
            if not products or (total and offset >= total):
                break

        return self._notification(
            _("Catálogo Fravega actualizado. Creados: %(created)s. Actualizados: %(updated)s. Omitidos: %(skipped)s.")
            % {"created": created_count, "updated": updated_count, "skipped": skipped_count}
        )

    @api.model
    def get_catalog_page(self, limit=24, offset=0, search=None):
        if search:
            domain = ["|", ("sku", "ilike", search), ("title", "ilike", search)]
            total = self.search_count(domain)
            records = self.search(domain, limit=limit, offset=offset)
        else:
            payload = self._fetch_page(limit, offset)
            products = payload.get("data") or []
            synced_skus, _created, _updated, _skipped = self._upsert_products(products)
            total = self._to_int(payload.get("total")) or (offset + len(products))
            records = self.search([("sku", "in", synced_skus)]) if synced_skus else self.browse()
        return {
            "items": [record._catalog_item() for record in records],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }

    def _catalog_item(self):
        self.ensure_one()
        return {
            "id": self.id,
            "sku": self.sku,
            "external_ref": self.ref_id,
            "title": self.title,
            "price": self.price_sale,
            "stock": self.stock,
            "status_label": self.item_state or self.status_code,
            "active": self.active,
            "thumbnail": self.thumbnail,
            "link": False,
        }

    def _notification(self, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Fravega"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
