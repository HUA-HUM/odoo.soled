import json
import logging
import re
from urllib.parse import quote

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MlCatalog(models.Model):
    """Lectura del catalogo de MercadoLibre que expone internal-api.

    No guarda nada: el panel lee en vivo, igual que el catalogo de Coresa.
    Es un Model y no un AbstractModel porque los abstractos no entran en
    ir.model y entonces no se les puede dar ACL, que es lo que habilita la
    llamada por RPC.
    """

    _name = "ml.catalog"
    _description = "Catalogo MercadoLibre"

    name = fields.Char(default="Catalogo ML")

    API_TIMEOUT = 60
    PRODUCTS_PATH = "/internal/mercadolibre/products"

    # ------------------------------------------------------------------
    @api.model
    def _api_base_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ml_catalog_panel.internal_api_base_url", "https://internal.solediluminacion.com")
            .rstrip("/")
        )

    @api.model
    def _api_key(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ml_catalog_panel.internal_api_key", "_internal")
            .strip()
        )

    @api.model
    def _api_get(self, path, params=None, silent=False):
        try:
            response = requests.get(
                "%s%s" % (self._api_base_url(), path),
                params=params or {},
                headers={"accept": "*/*", "x-internal-api-key": self._api_key()},
                timeout=self.API_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            if silent:
                _logger.info("API interna: %s fallo (%s)", path, error)
                return None
            raise UserError(
                _("Error consultando el catálogo de MercadoLibre: %s") % error
            ) from error
        except ValueError as error:
            if silent:
                return None
            raise UserError(_("El catálogo no devolvió JSON válido.")) from error

    # ------------------------------------------------------------------
    @api.model
    def get_catalog_page(self, page=1, limit=24):
        """Una pagina del catalogo.

        La API pagina por numero de pagina, no por offset, y devuelve las
        filas en "data". Se manda una fila liviana: el payload completo trae
        descripcion, atributos, fotos y el raw de ML, y son 6 KB por
        producto que el navegador no necesita para la grilla.
        """
        page = max(1, self._as_int(page) or 1)
        limit = min(max(1, self._as_int(limit) or 24), 100)
        payload = self._api_get(self.PRODUCTS_PATH, {"page": page, "limit": limit}) or {}
        payload = payload if isinstance(payload, dict) else {}
        items = payload.get("data") or payload.get("items") or []
        return {
            "items": [self._row_payload(item) for item in items if isinstance(item, dict)],
            "pagination": {
                "page": self._as_int(payload.get("page")) or page,
                "limit": self._as_int(payload.get("limit")) or limit,
                "total": self._as_int(payload.get("total")),
                "totalPages": self._as_int(payload.get("totalPages")),
            },
        }

    @api.model
    def find_product(self, query):
        """Busqueda exacta por SKU o por MLA.

        Un SKU puede tener varias publicaciones: JDTM1501 tiene 12. Por eso
        va por /by-sku, que las devuelve todas paginadas, y no por el
        identificador generico, que resuelve una sola y esconde el resto.
        La API no busca por texto: si no hay nada, se avisa en vez de
        devolver una grilla vacia que parece un filtro mal puesto.
        """
        query = str(query or "").strip()
        if not query:
            raise UserError(_("Ingresá un SKU o un MLA."))

        looks_like_mla = bool(re.match(r"^MLA\d+$", query, re.IGNORECASE))
        rows = []
        if looks_like_mla:
            rows = self._find_by_mla(query)
            if not rows:
                rows = self._find_by_sku(query)
        else:
            rows = self._find_by_sku(query)
            if not rows:
                # Ultimo intento: el identificador generico resuelve las dos
                # formas y cubre los SKU raros.
                rows = self._find_by_identifier(query)

        return {
            "items": [self._row_payload(row) for row in rows],
            "found": bool(rows),
            "query": query,
            "total": len(rows),
        }

    @api.model
    def _find_by_sku(self, sku):
        payload = self._api_get(
            "%s/by-sku/%s" % (self.PRODUCTS_PATH, quote(sku, safe="")),
            {"page": 1, "limit": 100},
            silent=True,
        )
        payload = payload if isinstance(payload, dict) else {}
        rows = payload.get("data") or payload.get("items") or []
        return [row for row in rows if isinstance(row, dict) and row.get("meli_item_id")]

    @api.model
    def _find_by_mla(self, mla):
        item = self._unwrap(
            self._api_get(
                "%s/by-mla/%s" % (self.PRODUCTS_PATH, quote(mla, safe="")), silent=True
            )
        )
        return [item] if item else []

    @api.model
    def _find_by_identifier(self, query):
        item = self._unwrap(
            self._api_get("%s/%s" % (self.PRODUCTS_PATH, quote(query, safe="")), silent=True)
        )
        return [item] if item else []

    @api.model
    def get_product_detail(self, meli_item_id):
        meli_item_id = str(meli_item_id or "").strip()
        if not meli_item_id:
            raise UserError(_("Falta la publicación."))
        payload = self._api_get(
            "%s/by-mla/%s" % (self.PRODUCTS_PATH, quote(meli_item_id, safe=""))
        )
        item = self._unwrap(payload)
        if not item:
            raise UserError(_("No encontramos la publicación %s.") % meli_item_id)
        return self._detail_payload(item)

    # ------------------------------------------------------------------
    @api.model
    def _unwrap(self, payload):
        """La API devuelve el item solo o envuelto en data segun la ruta."""
        if isinstance(payload, dict) and payload.get("data"):
            payload = payload["data"]
        if isinstance(payload, list):
            payload = payload[0] if payload else None
        return payload if isinstance(payload, dict) and payload.get("meli_item_id") else None

    @api.model
    def _secure(self, url):
        """Las miniaturas vienen en http y el panel corre en https: el
        navegador las bloquea por contenido mixto."""
        url = str(url or "")
        return url.replace("http://", "https://", 1) if url.startswith("http://") else url

    @api.model
    def _row_payload(self, item):
        return {
            "id": item.get("meli_item_id") or "",
            "sku": item.get("sku") or "",
            "title": item.get("title") or "",
            "status": item.get("status") or "",
            "price": self._as_float(item.get("price")),
            "available": self._as_int(item.get("available_quantity")),
            "sold": self._as_int(item.get("sold_quantity")),
            "listingType": item.get("listing_type_id") or "",
            "categoryName": item.get("category_name") or "",
            "brand": item.get("brand") or "",
            "thumbnail": self._secure(item.get("thumbnail")),
            "permalink": item.get("permalink") or "",
            "freeShipping": bool(self._as_int(item.get("free_shipping"))),
            "hasVariations": bool(self._as_int(item.get("has_variations"))),
            "updatedAt": item.get("updated_at") or "",
        }

    @api.model
    def _detail_payload(self, item):
        detail = self._row_payload(item)
        detail.update(
            {
                "description": item.get("description") or "",
                "basePrice": self._as_float(item.get("base_price")),
                "originalPrice": self._as_float(item.get("original_price")),
                "condition": item.get("condition_type") or "",
                "categoryId": item.get("category_id") or "",
                "categoryPath": self._category_path(item.get("category_path")),
                "domain": item.get("domain_id") or "",
                "model": item.get("model") or "",
                "gtin": item.get("gtin") or "",
                "buyingMode": item.get("buying_mode") or "",
                "catalogListing": bool(self._as_int(item.get("catalog_listing"))),
                "logisticType": item.get("logistic_type") or "",
                "shippingMode": item.get("shipping_mode") or "",
                "localPickUp": bool(self._as_int(item.get("local_pick_up"))),
                "variations": len(item.get("variations") or []),
                "installments": self._as_int(item.get("installments_quantity")),
                "createdAt": item.get("created_at") or "",
                "lastSeenAt": item.get("last_seen_at") or "",
                "pictures": [
                    self._secure(picture.get("secure_url") or picture.get("url"))
                    for picture in (item.get("pictures") or [])
                    if isinstance(picture, dict) and (picture.get("secure_url") or picture.get("url"))
                ],
                # Solo los que tienen valor: ML manda decenas en null.
                "attributes": [
                    {
                        "id": attribute.get("id") or "",
                        "name": attribute.get("name") or attribute.get("id") or "",
                        "value": str(attribute.get("value_name")),
                    }
                    for attribute in (item.get("attributes") or [])
                    if isinstance(attribute, dict) and attribute.get("value_name") not in (None, "")
                ],
            }
        )
        return detail

    @api.model
    def _category_path(self, value):
        """category_path viene como un JSON adentro de un string."""
        if isinstance(value, list):
            return [str(one) for one in value]
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, ValueError):
            return []
        return [str(one) for one in parsed] if isinstance(parsed, list) else []

    # ------------------------------------------------------------------
    @api.model
    def _as_int(self, value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @api.model
    def _as_float(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
