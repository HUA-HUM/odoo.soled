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

    can_publish = fields.Boolean(compute="_compute_can_publish")
    blocking_reason = fields.Char(compute="_compute_can_publish")

    @api.depends("sku", "family_name")
    def _compute_name(self):
        for publication in self:
            parts = [part for part in (publication.sku, publication.family_name) if part]
            publication.name = " — ".join(parts) or publication.sku or "Publicacion"

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
        if status_code in (400, 422) and detail:
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

    @api.model
    def _values_from_preview(self, sku, payload):
        draft = payload.get("draft")
        draft = draft if isinstance(draft, dict) else {}
        pictures = draft.get("pictures")
        pictures = pictures if isinstance(pictures, list) else []
        missing = payload.get("missingRequiredAttributes")
        missing = [str(item) for item in missing if item] if isinstance(missing, list) else []

        return {
            "sku": payload.get("sku") or sku,
            "publication_id": self._as_int(payload.get("publicationId")),
            "state": payload.get("status") or "draft",
            "family_name": draft.get("title") or "",
            "description": draft.get("description") or "",
            "category_id_ml": draft.get("category_id") or payload.get("categoryId") or "",
            "category_name": self._category_name(payload),
            "price": self._as_float(draft.get("price")),
            "available_quantity": self._as_int(draft.get("available_quantity")),
            "picture_url": pictures[0] if pictures else "",
            "missing_attributes": ", ".join(missing),
            "validation_message": self._validation_text(payload.get("validation")),
            "error_message": "",
            "raw_draft_json": json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            "coresa_snapshot_json": json.dumps(
                payload.get("coresaSnapshot") or {}, ensure_ascii=False, indent=2, default=str
            ),
            "ai_model": payload.get("aiModel") or "",
            "ai_generated_at": payload.get("aiGeneratedAt") or "",
            "category_suggestion_ids": [(5, 0, 0)] + [
                (0, 0, values) for values in self._category_values(payload)
            ],
            "attribute_ids": [(5, 0, 0)] + [
                (0, 0, values) for values in self._attribute_values(draft, missing)
            ],
        }

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
    attribute_id_ml = fields.Char(string="ID", readonly=True)
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
