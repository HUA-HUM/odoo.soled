import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoresaPublication(models.Model):
    _name = "coresa.publication"
    _description = "Publicacion Coresa en MercadoLibre"
    _order = "create_date desc"

    # El preview llama a Coresa, a ML y a OpenAI encadenados: con los 45s que
    # usa sku_publisher_panel se corta antes de que responda.
    API_TIMEOUT = 120

    STATE_SELECTION = [
        ("draft", "Borrador"),
        ("ready", "Listo para publicar"),
        ("publishing", "Publicando"),
        ("published", "Publicado"),
        ("partial", "Publicado parcialmente"),
        ("failed", "Con error"),
        ("discarded", "Descartado"),
    ]

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    sku = fields.Char(string="SKU", required=True, readonly=True, index=True)
    publication_id = fields.Integer(
        string="ID en coresa-api",
        readonly=True,
        help="Identificador que devuelve el preview y que se usa al publicar.",
    )
    state = fields.Selection(STATE_SELECTION, string="Estado", readonly=True, default="draft")

    family_name = fields.Char(string="Nombre en ML")
    description = fields.Text(string="Descripcion")
    category_id_ml = fields.Char(string="Categoria ML", readonly=True)
    category_name = fields.Char(string="Nombre de categoria", readonly=True)
    price = fields.Float(string="Precio")
    available_quantity = fields.Integer(string="Stock")
    picture_url = fields.Char(string="Imagen")

    attribute_ids = fields.One2many(
        "coresa.publication.attribute", "publication_ref", string="Atributos"
    )
    missing_attributes = fields.Char(string="Atributos obligatorios faltantes", readonly=True)
    validation_message = fields.Text(string="Validacion de MercadoLibre", readonly=True)

    classic_item_id = fields.Char(string="Publicacion clasica", readonly=True)
    premium_item_id = fields.Char(string="Publicacion premium", readonly=True)
    permalink = fields.Char(string="Link", readonly=True)
    error_message = fields.Text(string="Error", readonly=True)
    raw_draft_json = fields.Text(string="Borrador completo", readonly=True)
    coresa_snapshot_json = fields.Text(string="Datos crudos de Coresa", readonly=True)
    ai_model = fields.Char(string="Modelo de IA", readonly=True)
    ai_generated_at = fields.Char(string="Generado el", readonly=True)
    category_suggestion_ids = fields.One2many(
        "coresa.publication.category", "publication_ref", string="Categorias sugeridas"
    )

    has_missing = fields.Boolean(compute="_compute_flags")
    has_validation = fields.Boolean(compute="_compute_flags")
    has_error = fields.Boolean(compute="_compute_flags")
    has_picture = fields.Boolean(compute="_compute_flags")
    has_result = fields.Boolean(compute="_compute_flags")
    title_length = fields.Integer(compute="_compute_flags")

    can_publish = fields.Boolean(compute="_compute_can_publish")
    blocking_reason = fields.Char(compute="_compute_can_publish")

    @api.depends("sku", "family_name")
    def _compute_name(self):
        for publication in self:
            parts = [part for part in (publication.sku, publication.family_name) if part]
            publication.name = " — ".join(parts) or publication.sku or "Publicacion"

    @api.depends(
        "missing_attributes", "validation_message", "error_message",
        "picture_url", "classic_item_id", "premium_item_id", "family_name",
    )
    def _compute_flags(self):
        for publication in self:
            publication.has_missing = bool(publication.missing_attributes)
            publication.has_validation = bool(publication.validation_message)
            publication.has_error = bool(publication.error_message)
            publication.has_picture = bool(publication.picture_url)
            publication.has_result = bool(
                publication.classic_item_id or publication.premium_item_id
            )
            # ML corta el titulo a los 60 caracteres.
            publication.title_length = len(publication.family_name or "")

    @api.depends("publication_id", "state")
    def _compute_can_publish(self):
        for publication in self:
            reason = ""
            if publication.state == "published":
                reason = _("La publicación ya está completa.")
            elif publication.state == "discarded":
                reason = _("La publicación fue descartada.")
            elif publication.state == "publishing":
                reason = _("Se está publicando en este momento.")
            elif not publication.publication_id:
                reason = _(
                    "coresa-api no registró esta publicación todavía, así que no "
                    "hay identificador para publicar."
                )
            elif publication.state == "draft":
                # MercadoLibre rechaza el borrador: el detalle esta en
                # validation_message.
                reason = _(
                    "MercadoLibre todavía rechaza el borrador. Corregí lo que "
                    "aparece abajo y volvé a armarlo."
                )
            publication.blocking_reason = reason
            publication.can_publish = not reason

    # ------------------------------------------------------------------
    # coresa-api
    # ------------------------------------------------------------------
    @api.model
    def _api_base_url(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coresa_meli_publisher.coresa_api_base_url",
                "https://api.coresa.solediluminacion.com",
            )
            .rstrip("/")
        )

    @api.model
    def _api_key(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("coresa_meli_publisher.api_key", "")
            .strip()
        )

    @api.model
    def _api_request(self, method, path, payload=None):
        api_key = self._api_key()
        if not api_key:
            # Sin clave la API responde 401 y el mensaje no dice como arreglarlo.
            raise UserError(
                _(
                    "Falta configurar la clave de coresa-api. Cargala en "
                    "Ajustes → Técnico → Parámetros del sistema, en la clave "
                    "coresa_meli_publisher.api_key."
                )
            )
        url = "%s%s" % (self._api_base_url(), path)
        try:
            response = requests.request(
                method,
                url,
                json=payload or {},
                headers={
                    "Content-Type": "application/json",
                    "x-internal-api-key": api_key,
                },
                timeout=self.API_TIMEOUT,
            )
        except requests.RequestException as error:
            _logger.warning("coresa-api %s %s fallo: %s", method, url, error)
            raise UserError(
                _("No se pudo conectar con coresa-api: %s") % error
            ) from error

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            raise UserError(self._api_error_message(response.status_code, data))
        return data if isinstance(data, dict) else {}

    @api.model
    def _flatten_message(self, message):
        """NestJS manda `message` como string o como lista cuando falla el body."""
        if isinstance(message, (list, tuple)):
            return "\n".join(str(part) for part in message if part)
        return str(message or "").strip()

    @api.model
    def _api_error_message(self, status_code, data):
        data = data if isinstance(data, dict) else {}
        detail = self._flatten_message(data.get("message"))
        mapped = {
            401: _(
                "coresa-api rechazó la clave. Revisá "
                "coresa_meli_publisher.api_key en Parámetros del sistema."
            ),
            404: _("El SKU no existe en el catálogo de Coresa."),
            409: _("Ese SKU ya tiene una publicación en curso."),
            502: _("MercadoLibre no responde, probá de nuevo en unos minutos."),
            503: _("MercadoLibre no responde, probá de nuevo en unos minutos."),
        }.get(status_code)
        if status_code in (400, 404, 422) and detail:
            # El 404 puede ser del SKU o de la publicacion: el mensaje de la
            # API dice cual, el nuestro adivina mal la mitad de las veces.
            return detail
        if mapped and detail:
            return "%s\n\n%s" % (mapped, detail)
        return mapped or detail or (
            _("coresa-api respondió con un error (%s).") % status_code
        )

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    @api.model
    def _requested_by(self):
        return self.env.user.email or self.env.user.login or ""

    @api.model
    def preview_sku(self, sku, category_id=None):
        """Arma el borrador y devuelve los valores listos para crear/escribir.

        category_id rehace el borrador con otra de las categorias sugeridas:
        cada categoria tiene sus propios atributos obligatorios.
        """
        sku = str(sku or "").strip()
        if not sku:
            raise UserError(_("Ingresá un SKU."))
        body = {"sku": sku, "requestedBy": self._requested_by()}
        if category_id:
            body["categoryId"] = category_id
        payload = self._api_request("POST", "/coresa/publications/preview", body)
        return self._values_from_preview(sku, payload)

    # ------------------------------------------------------------------
    # Preview para el panel (sin tocar registros de Odoo)
    # ------------------------------------------------------------------
    @api.model
    def preview_payload(self, sku, category_id=None):
        """El borrador tal cual lo devuelve coresa-api, listo para mostrar.

        Es la misma llamada que usa el asistente, pero sin crear ni escribir
        nada en Odoo: la pantalla de previsualizar solo mira. La API igual
        deja su propio registro del lado de Coresa (devuelve publicationId).
        """
        sku = str(sku or "").strip()
        if not sku:
            raise UserError(_("Ingresá un SKU."))
        body = {"sku": sku, "requestedBy": self._requested_by()}
        if category_id:
            body["categoryId"] = category_id
        payload = self._api_request("POST", "/coresa/publications/preview", body)
        return self._preview_payload(payload, sku)

    @api.model
    def _preview_payload(self, payload, sku):
        payload = payload if isinstance(payload, dict) else {}
        draft = payload.get("draft") or {}
        draft = draft if isinstance(draft, dict) else {}
        shipping = draft.get("shipping") or {}
        category_id = payload.get("categoryId") or draft.get("category_id") or ""
        suggestions = [
            {
                "id": entry.get("category_id") or "",
                "name": entry.get("category_name") or "",
                "domain": entry.get("domain_name") or "",
            }
            for entry in (payload.get("categorySuggestions") or [])
            if isinstance(entry, dict) and entry.get("category_id")
        ]
        current = next((one for one in suggestions if one["id"] == category_id), None)
        return {
            "publicationId": self._as_int(payload.get("publicationId")),
            "sku": payload.get("sku") or sku,
            "status": payload.get("status") or "",
            "categoryId": category_id,
            "categoryName": (current or {}).get("name", ""),
            "categoryDomain": (current or {}).get("domain", ""),
            "suggestions": suggestions,
            # Los que ML pide para esta categoria y el borrador no trae: son
            # los que hacen fallar la validacion.
            "missing": [str(one) for one in (payload.get("missingRequiredAttributes") or [])],
            # Los que no estaban en Coresa y completo la IA. Van marcados en
            # la pantalla: son lo unico del borrador que nadie verifico.
            "inferred": [str(one) for one in (payload.get("inferredAttributes") or [])],
            "draft": {
                "title": draft.get("title") or "",
                "price": self._as_float(draft.get("price")),
                "quantity": self._as_int(draft.get("available_quantity")),
                "condition": draft.get("condition") or "",
                "pictures": [str(one) for one in (draft.get("pictures") or [])],
                "description": draft.get("description") or "",
                "listingTypes": [str(one) for one in (draft.get("listing_types") or [])],
                "shipping": {
                    "mode": shipping.get("mode") or "",
                    "freeShipping": bool(shipping.get("free_shipping")),
                },
                "attributes": self._attribute_rows(draft.get("attributes")),
                "saleTerms": self._attribute_rows(draft.get("sale_terms")),
            },
            "validation": self._validation_rows(payload.get("validation")),
        }

    @api.model
    def _attribute_rows(self, entries):
        rows = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            value = entry.get("value_name")
            if value in (None, ""):
                value = entry.get("value_id") or ""
            rows.append({"id": entry.get("id") or "", "value": str(value)})
        return rows

    @api.model
    def _validation_rows(self, validation):
        """Una fila por tipo de publicacion.

        ML contesta el motivo real adentro de error.cause; el message de
        arriba suele ser un "Validation error" que no dice nada.
        """
        validation = validation if isinstance(validation, dict) else {}
        results = validation.get("results") or {}
        rows = []
        for listing_type, result in (results.items() if isinstance(results, dict) else []):
            result = result if isinstance(result, dict) else {}
            error = result.get("error") or {}
            error = error if isinstance(error, dict) else {}
            rows.append(
                {
                    "listingType": listing_type,
                    "valid": bool(result.get("valid")),
                    # ML manda warnings y causes como objetos: lo unico que
                    # sirve mostrar es su message.
                    "warnings": self._messages(result.get("warnings")),
                    "errorCode": error.get("code") or "",
                    "errorMessage": error.get("message") or "",
                    "causes": self._messages(error.get("cause")),
                    "retryable": bool(error.get("retryable")),
                }
            )
        return sorted(rows, key=lambda row: row["listingType"])

    @api.model
    def _messages(self, entries):
        messages = []
        for entry in entries or []:
            if isinstance(entry, dict):
                text = entry.get("message") or entry.get("code") or ""
            else:
                text = str(entry or "")
            text = str(text).strip()
            if text:
                messages.append(text)
        return messages

    @api.model
    def _apply_values(self, record, values):
        """Crea o actualiza sacando los comandos de limpieza cuando no hay
        lineas previas que limpiar."""
        if record:
            record.write(values)
            return record
        clean = dict(values)
        for field_name in ("attribute_ids", "category_suggestion_ids"):
            commands = clean.get(field_name)
            if isinstance(commands, list):
                clean[field_name] = [cmd for cmd in commands if cmd and cmd[0] != 5]
        return self.create(clean)

    @api.model
    def _values_from_preview(self, sku, payload):
        draft = payload.get("draft")
        draft = draft if isinstance(draft, dict) else {}
        pictures = draft.get("pictures")
        pictures = pictures if isinstance(pictures, list) else []
        raw_missing = payload.get("missingRequiredAttributes")
        has_missing = isinstance(raw_missing, list)
        missing = [str(item) for item in raw_missing if item] if has_missing else []

        # El detalle usa "id" y no manda sugerencias ni faltantes; el preview
        # usa "publicationId" y los manda. Sirve para las dos formas.
        values = {
            "sku": payload.get("sku") or sku,
            "publication_id": self._as_int(
                payload.get("publicationId") or payload.get("id")
            ),
            "state": payload.get("status") or "draft",
            "family_name": draft.get("title") or "",
            "description": draft.get("description") or "",
            "category_id_ml": draft.get("category_id") or payload.get("categoryId") or "",
            "category_name": self._category_name(payload),
            "price": self._as_float(draft.get("price")),
            "available_quantity": self._as_int(draft.get("available_quantity")),
            "picture_url": pictures[0] if pictures else "",
            "missing_attributes": ", ".join(missing) if has_missing else "",
            "validation_message": self._validation_text(payload.get("validation")),
            "error_message": "",
            "raw_draft_json": json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            "coresa_snapshot_json": json.dumps(
                payload.get("coresaSnapshot") or {}, ensure_ascii=False, indent=2, default=str
            ),
            "ai_model": payload.get("aiModel") or "",
            "ai_generated_at": payload.get("aiGeneratedAt") or "",
            "attribute_ids": [(5, 0, 0)] + [
                (0, 0, entry) for entry in self._attribute_values(draft, missing)
            ],
        }
        if isinstance(payload.get("categorySuggestions"), list):
            values["category_suggestion_ids"] = [(5, 0, 0)] + [
                (0, 0, entry) for entry in self._category_values(payload)
            ]
        return values

    @api.model
    def _category_values(self, payload):
        values = []
        for suggestion in payload.get("categorySuggestions") or []:
            if not isinstance(suggestion, dict) or not suggestion.get("category_id"):
                continue
            values.append(
                {
                    "category_id_ml": suggestion.get("category_id"),
                    "name": suggestion.get("category_name") or "",
                    "domain_name": suggestion.get("domain_name") or "",
                }
            )
        return values

    @api.model
    def _category_name(self, payload):
        category_id = payload.get("categoryId")
        for suggestion in payload.get("categorySuggestions") or []:
            if isinstance(suggestion, dict) and suggestion.get("category_id") == category_id:
                return suggestion.get("category_name") or ""
        return ""

    @api.model
    def _attribute_values(self, draft, missing):
        values = []
        seen = set()
        for attribute in draft.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            attribute_id = str(attribute.get("id") or "").strip()
            if not attribute_id:
                continue
            seen.add(attribute_id)
            allowed = attribute.get("allowed_values") or attribute.get("values") or []
            values.append(
                {
                    "attribute_id_ml": attribute_id,
                    "name": attribute.get("name") or attribute_id,
                    "value": attribute.get("value_name") or attribute.get("value") or "",
                    "required": attribute_id in missing,
                    "allowed_values": ", ".join(
                        str(item) for item in allowed if item
                    ) if isinstance(allowed, list) else "",
                }
            )
        # Los obligatorios que faltan no vienen en el draft: hay que crearlos
        # vacios para que el usuario tenga donde completarlos.
        for attribute_id in missing:
            if attribute_id not in seen:
                values.append(
                    {
                        "attribute_id_ml": attribute_id,
                        "name": attribute_id,
                        "value": "",
                        "required": True,
                        "allowed_values": "",
                    }
                )
        return values

    @api.model
    def _validation_text(self, validation):
        validation = validation if isinstance(validation, dict) else {}
        results = validation.get("results")
        results = results if isinstance(results, dict) else {}
        lines = []
        for listing_type, result in results.items():
            if not isinstance(result, dict) or result.get("valid"):
                continue
            error = result.get("error")
            error = error if isinstance(error, dict) else {}
            label = {"gold_special": "Clásica", "gold_pro": "Premium"}.get(
                listing_type, listing_type
            )
            causes = [
                str(cause.get("message"))
                for cause in (error.get("cause") or [])
                if isinstance(cause, dict) and cause.get("message")
            ]
            detail = "; ".join(causes) or str(error.get("message") or "").strip()
            if detail:
                lines.append("%s: %s" % (label, detail))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Lectura del panel (los cuatro GET de coresa-api)
    # ------------------------------------------------------------------
    LIST_STATUSES = ("draft", "ready", "publishing", "published", "partial", "failed", "discarded")
    LIST_FILTERS = ("sku", "status", "categoryId", "from", "to")

    @api.model
    def _api_get(self, path, params=None):
        url = "%s%s" % (self._api_base_url(), path)
        api_key = self._api_key()
        if not api_key:
            raise UserError(
                _(
                    "Falta configurar la clave de coresa-api en el parámetro "
                    "coresa_meli_publisher.api_key."
                )
            )
        try:
            response = requests.get(
                url,
                params=params or {},
                headers={"x-internal-api-key": api_key},
                timeout=self.API_TIMEOUT,
            )
        except requests.RequestException as error:
            raise UserError(_("No se pudo conectar con coresa-api: %s") % error) from error
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            raise UserError(self._api_error_message(response.status_code, data))
        return data

    @api.model
    def get_publications_page(self, limit=25, offset=0, filters=None):
        params = {"limit": limit, "offset": offset}
        for key, value in (filters or {}).items():
            if key in self.LIST_FILTERS and str(value or "").strip():
                params[key] = str(value).strip()
        payload = self._api_get("/coresa/publications", params)
        payload = payload if isinstance(payload, dict) else {}
        pagination = payload.get("pagination") or {}
        return {
            "items": [
                self._row_payload(item)
                for item in (payload.get("items") or [])
                if isinstance(item, dict)
            ],
            "pagination": {
                "limit": self._as_int(pagination.get("limit")) or limit,
                "offset": self._as_int(pagination.get("offset")),
                "total": self._as_int(pagination.get("total")),
            },
        }

    @api.model
    def _row_payload(self, item):
        return {
            "id": self._as_int(item.get("id")),
            "sku": item.get("sku") or "",
            "status": item.get("status") or "",
            "title": item.get("title") or "",
            "categoryId": item.get("categoryId") or "",
            "price": self._as_float(item.get("price")),
            "availableQuantity": self._as_int(item.get("availableQuantity")),
            "classicItemId": item.get("classicItemId") or "",
            "premiumItemId": item.get("premiumItemId") or "",
            "permalink": item.get("permalink") or "",
            "errorMessage": item.get("errorMessage") or "",
            "requestedBy": item.get("requestedBy") or "",
            "publishedAt": item.get("publishedAt") or "",
            "createdAt": item.get("createdAt") or "",
            "updatedAt": item.get("updatedAt") or "",
        }

    # Lo que todavia no se mando: el publicador trabaja sobre esto.
    QUEUE_STATUSES = ("draft", "ready")

    @api.model
    def get_publisher_queue(self, limit=50):
        """Borradores y listos, en una sola lista.

        La API filtra por un estado por vez, asi que se piden los dos y se
        ordenan juntos por fecha: para el que publica son la misma cola.
        """
        items = []
        counters = {}
        for status in self.QUEUE_STATUSES:
            payload = self._api_get(
                "/coresa/publications", {"status": status, "limit": limit, "offset": 0}
            )
            payload = payload if isinstance(payload, dict) else {}
            rows = [
                self._row_payload(item)
                for item in (payload.get("items") or [])
                if isinstance(item, dict)
            ]
            counters[status] = self._as_int((payload.get("pagination") or {}).get("total"))
            items.extend(rows)
        items.sort(key=lambda row: row.get("createdAt") or "", reverse=True)
        return {"items": items, "counters": counters, "total": sum(counters.values())}

    @api.model
    def get_publication_counters(self):
        """Un total por estado. No hay endpoint de conteo: se pide el listado
        con limit=1 por estado y se lee pagination.total, como indica el
        instructivo."""
        counters = {}
        for status in self.LIST_STATUSES:
            try:
                payload = self._api_get(
                    "/coresa/publications", {"status": status, "limit": 1}
                )
                counters[status] = self._as_int(
                    (payload.get("pagination") or {}).get("total")
                )
            except UserError:
                counters[status] = 0
        return counters

    @api.model
    def get_publication_history(self, sku):
        sku = str(sku or "").strip()
        if not sku:
            return []
        payload = self._api_get(
            "/coresa/publications/by-sku/%s/history" % quote(sku, safe="")
        )
        return [
            self._row_payload(item) for item in (payload or []) if isinstance(item, dict)
        ]

    @api.model
    def open_publication(self, publication_id):
        """Trae el detalle y abre el editor sobre el espejo local."""
        publication_id = self._as_int(publication_id)
        if not publication_id:
            raise UserError(_("Publicación inválida."))
        payload = self._api_get("/coresa/publications/%s" % publication_id)
        payload = payload if isinstance(payload, dict) else {}
        values = self._values_from_preview(payload.get("sku") or "", payload)
        record = self._apply_values(
            self.search([("publication_id", "=", publication_id)], limit=1), values
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Borrador de publicación"),
            "res_model": "coresa.publication",
            "res_id": record.id,
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Editor del borrador (contra la API, sin espejo en Odoo)
    # ------------------------------------------------------------------
    EDITABLE_STATES = ("draft", "ready", "failed")

    @api.model
    def get_publication(self, publication_id):
        publication_id = self._as_int(publication_id)
        if not publication_id:
            raise UserError(_("Publicación inválida."))
        payload = self._api_get("/coresa/publications/%s" % publication_id)
        return self._editor_payload(payload if isinstance(payload, dict) else {})

    @api.model
    def save_draft(self, publication_id, draft):
        """Guarda las correcciones y revalida en ML. No publica.

        El estado lo decide MercadoLibre: si el borrador queda bien vuelve
        "ready" y si no, "draft". Por eso el front tiene que recalcular con
        la respuesta si Publicar va habilitado.
        """
        publication_id = self._as_int(publication_id)
        if not publication_id:
            raise UserError(_("Publicación inválida."))
        body = {"draft": self._draft_body(draft), "requestedBy": self._requested_by()}
        try:
            payload = self._api_request(
                "PUT", "/coresa/publications/%s/draft" % publication_id, body
            )
        except UserError as error:
            # El endpoint puede no estar desplegado todavia: el 404 generico
            # habla del SKU y manda a buscar donde no es.
            if "Cannot PUT" in str(error):
                raise UserError(
                    _(
                        "coresa-api todavía no tiene el endpoint para guardar "
                        "cambios (PUT /coresa/publications/%s/draft). El resto "
                        "de la pantalla funciona; guardar va a andar cuando se "
                        "despliegue esa versión."
                    )
                    % publication_id
                ) from error
            raise
        return self._editor_payload(payload)

    @api.model
    def publish_draft(self, publication_id):
        """Publica de verdad en MercadoLibre. No tiene vuelta atras desde acá."""
        publication_id = self._as_int(publication_id)
        if not publication_id:
            raise UserError(_("Publicación inválida."))
        payload = self._api_request(
            "POST",
            "/coresa/publications/%s/publish" % publication_id,
            {"requestedBy": self._requested_by()},
        )
        result = self._editor_payload(payload)
        # linkedForSync solo viene en la respuesta de publish.
        result["linkedForSync"] = bool(payload.get("linkedForSync"))
        return result

    @api.model
    def rebuild_draft(self, sku, category_id=None):
        """Rehace el borrador con la IA. Pisa las correcciones a mano."""
        return self.preview_payload(sku, category_id)

    @api.model
    def _draft_body(self, draft):
        """Lo que se manda en el PUT.

        attributes y pictures se reemplazan enteros del lado de la API, asi
        que van completos: mandar solo el que se toco borraria el resto.
        """
        draft = draft if isinstance(draft, dict) else {}
        body = {}
        for key, source in (
            ("title", "title"),
            ("description", "description"),
            ("category_id", "categoryId"),
        ):
            value = draft.get(source)
            if value is not None:
                body[key] = str(value).strip()
        if draft.get("price") is not None:
            body["price"] = self._as_float(draft.get("price"))
        if draft.get("quantity") is not None:
            body["available_quantity"] = self._as_int(draft.get("quantity"))
        if isinstance(draft.get("attributes"), list):
            attributes = []
            for entry in draft["attributes"]:
                if not isinstance(entry, dict) or not entry.get("id"):
                    continue
                value = str(entry.get("value") or "").strip()
                if not value:
                    continue
                attribute = {"id": str(entry["id"]).strip(), "value_name": value}
                # El value_id solo sirve si el valor no se edito a mano.
                if entry.get("valueId") and not entry.get("dirty"):
                    attribute["value_id"] = str(entry["valueId"])
                attributes.append(attribute)
            body["attributes"] = attributes
        if isinstance(draft.get("pictures"), list):
            body["pictures"] = [str(one).strip() for one in draft["pictures"] if str(one).strip()]
        return body

    @api.model
    def _editor_payload(self, payload):
        """Normaliza lo que devuelven detalle, preview, PUT y publish.

        Las cuatro respuestas traen el mismo borrador con distinto envoltorio:
        el detalle usa id y el resto publicationId, y solo el preview trae
        las categorias sugeridas.
        """
        payload = payload if isinstance(payload, dict) else {}
        draft = payload.get("draft") or {}
        draft = draft if isinstance(draft, dict) else {}
        shipping = draft.get("shipping") or {}
        status = payload.get("status") or ""
        inferred = [str(one) for one in (payload.get("inferredAttributes") or [])]
        suggestions = [
            {
                "id": entry.get("category_id") or "",
                "name": entry.get("category_name") or "",
                "domain": entry.get("domain_name") or "",
            }
            for entry in (payload.get("categorySuggestions") or [])
            if isinstance(entry, dict) and entry.get("category_id")
        ]
        category_id = payload.get("categoryId") or draft.get("category_id") or ""
        current = next((one for one in suggestions if one["id"] == category_id), None)
        return {
            "id": self._as_int(payload.get("id") or payload.get("publicationId")),
            "sku": payload.get("sku") or draft.get("sku") or "",
            "status": status,
            "statusLabel": dict(self.STATE_SELECTION).get(status, status or "—"),
            "categoryId": category_id,
            "categoryName": (current or {}).get("name", ""),
            "suggestions": suggestions,
            "missing": [str(one) for one in (payload.get("missingRequiredAttributes") or [])],
            "inferred": inferred,
            "canEdit": status in self.EDITABLE_STATES,
            "canPublish": status == "ready",
            "draft": {
                "title": draft.get("title") or "",
                "description": draft.get("description") or "",
                "price": self._as_float(draft.get("price")),
                "quantity": self._as_int(draft.get("available_quantity")),
                "condition": draft.get("condition") or "",
                "pictures": [str(one) for one in (draft.get("pictures") or [])],
                "listingTypes": [str(one) for one in (draft.get("listing_types") or [])],
                "shipping": {
                    "mode": shipping.get("mode") or "",
                    "freeShipping": bool(shipping.get("free_shipping")),
                },
                "attributes": self._editor_attributes(draft.get("attributes"), inferred),
                "saleTerms": self._attribute_rows(draft.get("sale_terms")),
            },
            "validation": self._validation_rows(payload.get("validation")),
            "links": {
                "classicItemId": payload.get("classicItemId") or "",
                "premiumItemId": payload.get("premiumItemId") or "",
                "permalink": payload.get("permalink") or "",
            },
            "meta": {
                "requestedBy": payload.get("requestedBy") or "",
                "aiModel": payload.get("aiModel") or "",
                "aiGeneratedAt": payload.get("aiGeneratedAt") or "",
                "createdAt": payload.get("createdAt") or "",
                "updatedAt": payload.get("updatedAt") or "",
                "publishedAt": payload.get("publishedAt") or "",
                "errorMessage": payload.get("errorMessage") or "",
            },
        }

    @api.model
    def _editor_attributes(self, entries, inferred):
        rows = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            attribute_id = str(entry.get("id") or "")
            rows.append(
                {
                    "id": attribute_id,
                    "value": str(entry.get("value_name") or ""),
                    "valueId": str(entry.get("value_id") or ""),
                    "inferred": attribute_id in inferred,
                    "dirty": False,
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Acciones del formulario
    # ------------------------------------------------------------------
    def action_rebuild_draft(self):
        self.ensure_one()
        self.write(self.preview_sku(self.sku, self.category_id_ml))
        return True

    def action_discard(self):
        self.ensure_one()
        if self.state == "published":
            raise UserError(_("No se puede descartar una publicación ya realizada."))
        self.state = "discarded"
        return True

    def _publish_payload(self):
        self.ensure_one()
        attributes = [
            {"id": line.attribute_id_ml, "value_name": line.value}
            for line in self.attribute_ids
            if line.attribute_id_ml and line.value
        ]
        draft = dict(self._stored_draft())
        draft.update(
            {
                "title": self.family_name or "",
                "description": self.description or "",
                "category_id": self.category_id_ml or "",
                "price": self.price,
                "available_quantity": self.available_quantity,
                # El array de atributos se reemplaza entero, no se mergea:
                # van todos los del borrador con los cambios aplicados.
                "attributes": attributes,
            }
        )
        if self.picture_url:
            draft["pictures"] = [self.picture_url]
        return {"draft": draft, "requestedBy": self._requested_by()}

    def _stored_draft(self):
        """El borrador tal como vino, para no perder sale_terms ni shipping."""
        self.ensure_one()
        try:
            payload = json.loads(self.raw_draft_json or "{}")
        except ValueError:
            return {}
        draft = payload.get("draft")
        return draft if isinstance(draft, dict) else {}

    def action_publish(self):
        self.ensure_one()
        if not self.can_publish:
            raise UserError(self.blocking_reason or _("No se puede publicar todavía."))
        payload = self._api_request(
            "POST",
            "/coresa/publications/%s/publish" % self.publication_id,
            self._publish_payload(),
        )
        self.write(self._values_from_publish(payload))
        return True

    def _values_from_publish(self, payload):
        results = payload.get("results")
        results = results if isinstance(results, dict) else {}
        errors = []
        for listing_type, result in results.items():
            if isinstance(result, dict) and not result.get("ok"):
                error = result.get("error")
                error = error if isinstance(error, dict) else {}
                label = {"gold_special": "Clásica", "gold_pro": "Premium"}.get(
                    listing_type, listing_type
                )
                causes = [
                    str(cause.get("message"))
                    for cause in (error.get("cause") or [])
                    if isinstance(cause, dict) and cause.get("message")
                ]
                detail = "; ".join(causes) or str(error.get("message") or "").strip()
                errors.append("%s: %s" % (label, detail or _("sin detalle")))
        return {
            "state": payload.get("status") or "failed",
            "classic_item_id": payload.get("classicItemId") or "",
            "premium_item_id": payload.get("premiumItemId") or "",
            "permalink": payload.get("permalink") or "",
            "error_message": "\n".join(errors),
        }

    def action_open_permalink(self):
        self.ensure_one()
        if not self.permalink:
            raise UserError(_("Esta publicación todavía no tiene link."))
        return {"type": "ir.actions.act_url", "url": self.permalink, "target": "new"}

    # ------------------------------------------------------------------
    @api.model
    def _as_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @api.model
    def _as_float(self, value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


class CoresaPublicationAttribute(models.Model):
    _name = "coresa.publication.attribute"
    _description = "Atributo de una publicacion Coresa"
    _order = "required desc, name"

    publication_ref = fields.Many2one(
        "coresa.publication", string="Publicacion", required=True, ondelete="cascade", index=True
    )
    attribute_id_ml = fields.Char(string="ID en MercadoLibre", readonly=True)
    name = fields.Char(string="Atributo", readonly=True)
    value = fields.Char(string="Valor")
    required = fields.Boolean(string="Obligatorio", readonly=True)
    allowed_values = fields.Char(string="Valores permitidos", readonly=True)
    missing = fields.Boolean(compute="_compute_missing")

    @api.depends("required", "value")
    def _compute_missing(self):
        for line in self:
            line.missing = line.required and not line.value


class CoresaPublicationCategory(models.Model):
    _name = "coresa.publication.category"
    _description = "Categoria sugerida por MercadoLibre"

    publication_ref = fields.Many2one(
        "coresa.publication", string="Publicacion", required=True, ondelete="cascade", index=True
    )
    category_id_ml = fields.Char(string="Categoria", readonly=True)
    name = fields.Char(string="Nombre", readonly=True)
    domain_name = fields.Char(string="Dominio", readonly=True)

    def action_use_category(self):
        """Rehace el borrador con esta categoria."""
        self.ensure_one()
        publication = self.publication_ref
        publication.write(
            publication.preview_sku(publication.sku, self.category_id_ml)
        )
        return True
