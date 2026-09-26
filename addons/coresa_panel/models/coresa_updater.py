from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoresaUpdater(models.Model):
    """Lo que el actualizador de Coresa tiene registrado en MercadoLibre.

    La lista viene de /internal/coresa/products-in-mercadolibre, que solo
    guarda sku, mla y los dos flags. Para que la grilla sirva de algo se
    completa con el feed de Coresa en una sola llamada bulk, en vez de una
    por fila. El dato de MercadoLibre (precio, stock, estado publicado) se
    pide recien al abrir el detalle: ahi si es una consulta por MLA.

    No guarda nada: es un Model y no un AbstractModel solo porque los
    abstractos no entran en ir.model y entonces no se les puede dar ACL,
    que es lo que habilita la llamada por RPC.
    """

    _name = "coresa.updater"
    _description = "Actualizador Coresa"

    name = fields.Char(default="Actualizador")

    LIST_PATH = "/internal/coresa/products-in-mercadolibre"
    # updateStock y updatePrice viajan como string: la API los declara asi.
    LIST_FILTERS = ("sku", "mla", "updateStock", "updatePrice")
    CHANGES_LIMIT = 20
    SUMMARY_PAGE_SIZE = 500
    SUMMARY_MAX_PAGES = 10

    # ------------------------------------------------------------------
    @api.model
    def _catalog(self):
        """El cliente de la API interna vive en coresa.catalog."""
        return self.env["coresa.catalog"]

    # ------------------------------------------------------------------
    @api.model
    def get_updater_page(self, limit=24, offset=0, filters=None):
        catalog = self._catalog()
        params = {"limit": limit, "offset": offset}
        for key, value in (filters or {}).items():
            if key in self.LIST_FILTERS and str(value or "").strip():
                params[key] = str(value).strip()

        payload = catalog._api_get(self.LIST_PATH, params) or {}
        payload = payload if isinstance(payload, dict) else {}
        items = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
        products = self._products_by_sku([item.get("sku") for item in items])

        pagination = payload.get("pagination") or {}
        return {
            "items": [
                self._row_payload(item, products.get(item.get("sku") or ""))
                for item in items
            ],
            "pagination": {
                "limit": catalog._as_int(pagination.get("limit")) or limit,
                "offset": catalog._as_int(pagination.get("offset")),
                "total": catalog._as_int(pagination.get("total")),
            },
        }

    @api.model
    def get_updater_summary(self):
        """Los totales del encabezado.

        Recorre la lista cruda (sin completar con el feed, que es la parte
        cara) porque hace falta contar SKU distintos: hoy hay 432
        publicaciones sobre 175 SKU, asi que "cantidad de filas" y "cantidad
        de productos" no son lo mismo y conviene que se vea.
        """
        catalog = self._catalog()
        totals = {"total": 0, "skus": 0, "stock": 0, "price": 0}
        skus = set()
        offset = 0
        for _page in range(self.SUMMARY_MAX_PAGES):
            payload = catalog._api_get(
                self.LIST_PATH, {"limit": self.SUMMARY_PAGE_SIZE, "offset": offset}
            ) or {}
            items = [item for item in ((payload or {}).get("items") or []) if isinstance(item, dict)]
            totals["total"] = catalog._as_int(((payload or {}).get("pagination") or {}).get("total"))
            for item in items:
                if item.get("sku"):
                    skus.add(item["sku"])
                if item.get("updateStock"):
                    totals["stock"] += 1
                if item.get("updatePrice"):
                    totals["price"] += 1
            offset += len(items)
            if not items or offset >= totals["total"]:
                break
        totals["skus"] = len(skus)
        return totals

    @api.model
    def get_sku_detail(self, sku, mla=None):
        """Ficha completa: Coresa, MercadoLibre y el historial del sync."""
        catalog = self._catalog()
        sku = (sku or "").strip()
        detail = {
            "sku": sku,
            "product": None,
            "meli": None,
            "publications": [],
            "changes": [],
            "errors": [],
        }
        if not sku:
            return detail

        products = self._products_by_sku([sku])
        raw = products.get(sku)
        if raw:
            detail["product"] = catalog._product_payload(raw)
        else:
            detail["errors"].append("El SKU ya no figura en el catálogo de Coresa.")

        publications = catalog._api_get("%s/by-sku/%s" % (self.LIST_PATH, sku)) or []
        if isinstance(publications, dict):
            publications = publications.get("items") or []
        detail["publications"] = [
            {
                "mla": entry.get("mla") or "",
                "updateStock": bool(entry.get("updateStock")),
                "updatePrice": bool(entry.get("updatePrice")),
                "createdAt": entry.get("createdAt") or "",
            }
            for entry in publications
            if isinstance(entry, dict)
        ]

        mla = (mla or "").strip() or (detail["publications"][0]["mla"] if detail["publications"] else "")
        if mla:
            detail["meli"] = self._meli_payload(mla)
            if detail["meli"] is None:
                detail["errors"].append("La publicación %s no está en el espejo de MercadoLibre." % mla)

        changes = catalog._api_get(
            "/internal/coresa/meli-sync-changes/by-sku/%s" % sku,
            {"limit": self.CHANGES_LIMIT, "offset": 0},
        ) or {}
        detail["changes"] = [
            self._change_payload(entry)
            for entry in ((changes or {}).get("items") or [])
            if isinstance(entry, dict)
        ]
        return detail

    # ------------------------------------------------------------------
    # Acciones: que publicaciones mira el actualizador y que les toca
    # ------------------------------------------------------------------
    @api.model
    def get_actions_counters(self):
        """Los tres cortes con los que se revisa esto.

        Cada uno sale del total que devuelve la paginacion, pidiendo una
        sola fila: no hace falta traerlas.
        """
        catalog = self._catalog()
        cuts = {
            "all": {},
            "synced": {"updateStock": "true", "updatePrice": "true"},
            "excluded": {"updateStock": "false", "updatePrice": "false"},
        }
        counters = {}
        for key, params in cuts.items():
            payload = catalog._api_get(self.LIST_PATH, dict(params, limit=1, offset=0)) or {}
            counters[key] = catalog._as_int(((payload or {}).get("pagination") or {}).get("total"))
        return counters

    @api.model
    def _flag_values(self, update_stock=None, update_price=None):
        """Solo viajan las banderas que se quieren cambiar: la API deja
        intacta la que no venga."""
        values = {}
        if update_stock is not None:
            values["updateStock"] = bool(update_stock)
        if update_price is not None:
            values["updatePrice"] = bool(update_price)
        if not values:
            raise UserError(_("No se indicó qué cambiar."))
        return values

    @api.model
    def set_publication_flags(self, mla, update_stock=None, update_price=None):
        """Cambia las banderas de una publicacion puntual."""
        mla = (mla or "").strip()
        if not mla:
            raise UserError(_("Falta la publicación (MLA)."))
        values = self._flag_values(update_stock, update_price)
        payload = self._catalog()._api_write(
            "PATCH", "%s/by-mla/%s" % (self.LIST_PATH, quote(mla, safe="")), values
        )
        return self._flags_payload(payload)

    @api.model
    def set_sku_flags(self, sku, update_stock=None, update_price=None):
        """Cambia las banderas de todas las publicaciones de un SKU.

        Un SKU puede tener varias MLA (clasica y premium, por ejemplo) y
        casi siempre se quiere lo mismo para todas.
        """
        sku = (sku or "").strip()
        if not sku:
            raise UserError(_("Falta el SKU."))
        values = self._flag_values(update_stock, update_price)
        payload = self._catalog()._api_write(
            "PATCH", "%s/by-sku/%s" % (self.LIST_PATH, quote(sku, safe="")), values
        )
        return {
            "updated": self._catalog()._as_int((payload or {}).get("updated")),
            "items": [
                self._flags_payload(item)
                for item in ((payload or {}).get("items") or [])
                if isinstance(item, dict)
            ],
        }

    @api.model
    def link_publication(self, sku, mla, update_stock=True, update_price=True):
        """Da de alta el vinculo SKU ↔ MLA.

        Es un upsert por el par: si ya existe, la API actualiza las
        banderas en vez de fallar.
        """
        sku = (sku or "").strip()
        mla = (mla or "").strip()
        if not sku or not mla:
            raise UserError(_("Hacen falta el SKU y la publicación (MLA)."))
        payload = self._catalog()._api_write(
            "POST",
            self.LIST_PATH,
            {
                "sku": sku,
                "mla": mla,
                "updateStock": bool(update_stock),
                "updatePrice": bool(update_price),
            },
        )
        return self._flags_payload(payload)

    @api.model
    def _flags_payload(self, item):
        item = item if isinstance(item, dict) else {}
        return {
            "sku": item.get("sku") or "",
            "mla": item.get("mla") or "",
            "updateStock": bool(item.get("updateStock")),
            "updatePrice": bool(item.get("updatePrice")),
            "createdAt": item.get("createdAt") or "",
        }

    # ------------------------------------------------------------------
    @api.model
    def _products_by_sku(self, skus):
        """Feed de Coresa para varios SKU en una sola llamada."""
        wanted = [str(sku).strip() for sku in skus if str(sku or "").strip()]
        if not wanted:
            return {}
        payload = self._catalog()._api_post(
            "/internal/coresa/products/by-sku/bulk", {"skus": sorted(set(wanted))}
        ) or {}
        return {
            item.get("SKU"): item
            for item in ((payload or {}).get("items") or [])
            if isinstance(item, dict) and item.get("SKU")
        }

    @api.model
    def _meli_payload(self, mla):
        catalog = self._catalog()
        item = catalog._api_get("/internal/mercadolibre/products/by-mla/%s" % mla, silent=True)
        if isinstance(item, dict) and item.get("data"):
            item = item["data"]
        if not isinstance(item, dict) or not item.get("meli_item_id"):
            return None
        return {
            "mla": item.get("meli_item_id") or mla,
            "title": item.get("title") or "",
            "status": item.get("status") or "",
            "price": catalog._as_float(item.get("price")),
            "basePrice": catalog._as_float(item.get("base_price")),
            "available": catalog._as_int(item.get("available_quantity")),
            "sold": catalog._as_int(item.get("sold_quantity")),
            "listingType": item.get("listing_type_id") or "",
            "permalink": item.get("permalink") or "",
            "thumbnail": item.get("thumbnail") or "",
            "freeShipping": bool(item.get("free_shipping")),
            "catalogListing": bool(item.get("catalog_listing")),
            "updatedAt": item.get("updated_at") or "",
        }

    @api.model
    def _change_payload(self, entry):
        catalog = self._catalog()
        return {
            "id": entry.get("id"),
            "result": entry.get("result") or "",
            "source": entry.get("source") or "",
            "mla": entry.get("mla") or "",
            "priceBefore": catalog._as_float(entry.get("priceBefore")),
            "priceApplied": catalog._as_float(entry.get("priceApplied")),
            "stockBefore": catalog._as_int(entry.get("stockBefore")),
            "stockApplied": catalog._as_int(entry.get("stockApplied")),
            "errorMessage": entry.get("errorMessage") or "",
            "createdAt": entry.get("createdAt") or "",
        }

    # ------------------------------------------------------------------
    @api.model
    def _row_payload(self, item, product):
        product = product if isinstance(product, dict) else {}
        catalog = self._catalog()
        return {
            "sku": item.get("sku") or "",
            "mla": item.get("mla") or "",
            "updateStock": bool(item.get("updateStock")),
            "updatePrice": bool(item.get("updatePrice")),
            "createdAt": item.get("createdAt") or "",
            # Lo que sigue sale del feed de Coresa. Si el SKU ya no esta en el
            # feed queda vacio y la fila se marca: es una publicacion viva en
            # MercadoLibre que el actualizador ya no puede tocar.
            "inCatalog": bool(product),
            "description": product.get("Descripcion") or "",
            "brand": product.get("Marca") or "",
            "family": product.get("Sub_Familia") or "",
            "available": catalog._as_int(product.get("Disponible")),
            "priceList": catalog._as_float(product.get("Precio_Lista_1")),
            "currency": product.get("Moneda") or "",
            "image": product.get("URL_Imagen") or "",
        }
