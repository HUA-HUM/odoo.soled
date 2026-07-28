import json
import logging
from datetime import datetime, timezone

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class MlProduct(models.Model):
    _name = "ml.product"
    _description = "MercadoLibre Product"
    _order = "updated_at desc, id desc"

    ml_internal_id = fields.Char(string="ID interno", index=True)
    meli_item_id = fields.Char(string="ID MercadoLibre", required=True, index=True)
    seller_id = fields.Char(string="Seller ID", index=True)
    sku = fields.Char(string="SKU", index=True)
    title = fields.Char(string="Titulo", index=True)
    description = fields.Text(string="Descripcion")
    condition_type = fields.Char(string="Condicion")
    status = fields.Char(string="Estado", index=True)
    permalink = fields.Char(string="Link MercadoLibre")
    price = fields.Float(string="Precio")
    base_price = fields.Float(string="Precio base")
    original_price = fields.Float(string="Precio original")
    available_quantity = fields.Integer(string="Stock disponible")
    sold_quantity = fields.Integer(string="Cantidad vendida")
    listing_type_id = fields.Char(string="Tipo de publicacion")
    buying_mode = fields.Char(string="Modo de compra")
    catalog_listing = fields.Boolean(string="Catalog listing")
    category_id = fields.Char(string="ID categoria")
    category_name = fields.Char(string="Categoria", index=True)
    category_path = fields.Char(string="Ruta categoria")
    domain_id = fields.Char(string="Dominio")
    brand = fields.Char(string="Marca", index=True)
    model = fields.Char(string="Modelo")
    gtin = fields.Char(string="GTIN")
    thumbnail = fields.Char(string="Imagen principal")
    video_id = fields.Char(string="Video ID")
    logistic_type = fields.Char(string="Tipo de logistica")
    shipping_mode = fields.Char(string="Modo de envio")
    free_shipping = fields.Boolean(string="Envio gratis")
    local_pick_up = fields.Boolean(string="Retiro local")
    has_variations = fields.Boolean(string="Tiene variaciones")
    last_webhook_at = fields.Datetime(string="Ultimo webhook")
    last_seen_at = fields.Datetime(string="Ultima vista")
    created_at = fields.Datetime(string="Creado en")
    updated_at = fields.Datetime(string="Actualizado en")
    attributes_json = fields.Text(string="Atributos JSON")
    pictures_json = fields.Text(string="Imagenes JSON")
    variations_json = fields.Text(string="Variaciones JSON")
    raw_payload_json = fields.Text(string="Raw payload JSON")
    payload_json = fields.Text(string="Payload completo JSON")

    _sql_constraints = [
        (
            "meli_item_id_unique",
            "unique(meli_item_id)",
            "El ID de MercadoLibre ya existe en el catalogo.",
        )
    ]

    @api.model
    def _api_base_url(self):
        return "https://internal.solediluminacion.com/internal/mercadolibre/products"

    @api.model
    def _api_headers(self):
        return {
            "accept": "*/*",
            "x-internal-api-key": "_internal",
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
    def _to_bool(self, value):
        return bool(self._to_int(value)) if isinstance(value, (int, str)) else bool(value)

    @api.model
    def _to_datetime(self, value):
        if not value:
            return False
        if isinstance(value, datetime):
            dt_value = value
        else:
            try:
                dt_value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                _logger.warning("Invalid MercadoLibre datetime value: %s", value)
                return False
        if dt_value.tzinfo:
            dt_value = dt_value.astimezone(timezone.utc).replace(tzinfo=None)
        return fields.Datetime.to_string(dt_value)

    @api.model
    def _to_json(self, value):
        return json.dumps(value if value is not None else [], ensure_ascii=False, indent=2)

    @api.model
    def _prepare_product_values(self, product):
        return {
            "ml_internal_id": product.get("id"),
            "meli_item_id": product.get("meli_item_id"),
            "seller_id": product.get("seller_id"),
            "sku": product.get("sku"),
            "title": product.get("title"),
            "description": product.get("description"),
            "condition_type": product.get("condition_type"),
            "status": product.get("status"),
            "permalink": product.get("permalink"),
            "price": self._to_float(product.get("price")),
            "base_price": self._to_float(product.get("base_price")),
            "original_price": self._to_float(product.get("original_price")),
            "available_quantity": self._to_int(product.get("available_quantity")),
            "sold_quantity": self._to_int(product.get("sold_quantity")),
            "listing_type_id": product.get("listing_type_id"),
            "buying_mode": product.get("buying_mode"),
            "catalog_listing": self._to_bool(product.get("catalog_listing")),
            "category_id": product.get("category_id"),
            "category_name": product.get("category_name"),
            "category_path": product.get("category_path"),
            "domain_id": product.get("domain_id"),
            "brand": product.get("brand"),
            "model": product.get("model"),
            "gtin": product.get("gtin"),
            "thumbnail": product.get("thumbnail"),
            "video_id": product.get("video_id"),
            "logistic_type": product.get("logistic_type"),
            "shipping_mode": product.get("shipping_mode"),
            "free_shipping": self._to_bool(product.get("free_shipping")),
            "local_pick_up": self._to_bool(product.get("local_pick_up")),
            "has_variations": self._to_bool(product.get("has_variations")),
            "last_webhook_at": self._to_datetime(product.get("last_webhook_at")),
            "last_seen_at": self._to_datetime(product.get("last_seen_at")),
            "created_at": self._to_datetime(product.get("created_at")),
            "updated_at": self._to_datetime(product.get("updated_at")),
            "attributes_json": self._to_json(product.get("attributes")),
            "pictures_json": self._to_json(product.get("pictures")),
            "variations_json": self._to_json(product.get("variations")),
            "raw_payload_json": self._to_json(product.get("raw_payload")),
            "payload_json": self._to_json(product),
        }

    def action_open_permalink(self):
        self.ensure_one()
        if not self.permalink:
            raise UserError(_("Este producto no tiene permalink de MercadoLibre."))
        return {
            "type": "ir.actions.act_url",
            "url": self.permalink,
            "target": "new",
        }

    @api.model
    def action_sync_products(self):
        limit = 100
        page = 1
        total_pages = 1
        created_count = 0
        updated_count = 0
        skipped_count = 0

        while page <= total_pages:
            try:
                response = requests.get(
                    self._api_base_url(),
                    headers=self._api_headers(),
                    params={"page": page, "limit": limit},
                    timeout=60,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as error:
                raise UserError(_("Error consultando la API interna: %s") % error) from error
            except ValueError as error:
                raise UserError(_("La API interna no devolvio JSON valido.")) from error

            products = payload.get("data") or []
            total_pages = self._to_int(payload.get("totalPages")) or 1

            for product in products:
                if not product.get("meli_item_id"):
                    skipped_count += 1
                    continue

                values = self._prepare_product_values(product)
                existing = self.search(
                    [("meli_item_id", "=", product["meli_item_id"])],
                    limit=1,
                )
                if existing:
                    existing.write(values)
                    updated_count += 1
                else:
                    self.create(values)
                    created_count += 1

            page += 1

        message = _(
            "Sincronizacion finalizada. Creados: %(created)s. Actualizados: %(updated)s. Omitidos: %(skipped)s."
        ) % {
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
        }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("MercadoLibre"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
