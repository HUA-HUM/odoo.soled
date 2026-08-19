import json

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RetailerMarketplaceChange(models.Model):
    _name = "retailer.marketplace.change"
    _description = "Marketplace Change Action"
    _order = "external_created_at desc, id desc"

    action_id = fields.Char(string="ID acción", required=True, index=True)
    sku = fields.Char(string="SKU", index=True)
    marketplace = fields.Char(string="Marketplace", index=True)
    status = fields.Char(string="Estado", index=True)
    change_type = fields.Char(string="Tipo de cambio", index=True)
    summary = fields.Char(string="Resumen")
    old_value_json = fields.Text(string="Valor anterior JSON")
    new_value_json = fields.Text(string="Valor nuevo JSON")
    error_message = fields.Text(string="Error")
    external_created_at = fields.Datetime(string="Creado en origen")
    external_updated_at = fields.Datetime(string="Actualizado en origen")
    synced_at = fields.Datetime(string="Sincronizado en")
    payload_json = fields.Text(string="Payload listado JSON")
    detail_json = fields.Text(string="Payload detalle JSON")

    _sql_constraints = [
        ("action_id_unique", "unique(action_id)", "La acción de cambio ya existe."),
    ]

    @api.model
    def _api_base_url(self):
        return "https://internal.solediluminacion.com/internal/marketplace-change-actions"

    @api.model
    def _api_headers(self):
        return {"accept": "application/json", "x-internal-api-key": "_internal"}

    @api.model
    def _payload_value(self, payload, *keys, default=None):
        for key in keys:
            if key in payload and payload.get(key) is not None:
                return payload.get(key)
        return default

    @api.model
    def _parse_datetime(self, value):
        if not value:
            return False
        return str(value).replace("T", " ").replace("Z", "").split(".")[0][:19]

    @api.model
    def _format_money(self, value):
        if value is None or value == "":
            return "—"
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return str(value)
        return "${:,.0f}".format(amount).replace(",", ".")

    @api.model
    def _format_or_dash(self, value):
        if value is None or value == "":
            return "—"
        return str(value)

    @api.model
    def _build_summary(self, change_type, old_value, new_value):
        old_value = old_value if isinstance(old_value, dict) else {}
        new_value = new_value if isinstance(new_value, dict) else {}

        if change_type == "price":
            return "Precio: {} → {}".format(
                self._format_money(old_value.get("price")),
                self._format_money(new_value.get("price")),
            )

        if change_type == "stock":
            return "Stock: {} → {}".format(
                self._format_or_dash(old_value.get("stock")),
                self._format_or_dash(new_value.get("stock")),
            )

        if change_type == "status":
            return "Estado: {} → {}".format(
                self._format_or_dash(old_value.get("status")),
                self._format_or_dash(new_value.get("status")),
            )

        return False

    @api.model
    def _fetch_page(self, limit, offset, sku=None, marketplace=None, status=None):
        params = {"limit": limit, "offset": offset}
        if sku:
            params["sku"] = sku
        if marketplace:
            params["marketplace"] = marketplace
        if status:
            params["status"] = status
        try:
            response = requests.get(
                self._api_base_url(),
                headers=self._api_headers(),
                params=params,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando cambios: %s") % error) from error
        except ValueError as error:
            raise UserError(_("El servicio de cambios no devolvió JSON válido.")) from error

    @api.model
    def get_analytics(self, date=None, marketplace=None, status=None, source=None):
        allowed_marketplaces = {"oncity", "fravega"}
        allowed_statuses = {"queued", "processing", "completed", "failed", "skipped", "cancelled"}

        if marketplace and marketplace not in allowed_marketplaces:
            raise UserError(_("Marketplace inválido."))
        if status and status not in allowed_statuses:
            raise UserError(_("Estado inválido."))
        if date:
            try:
                date = fields.Date.to_string(fields.Date.to_date(date))
            except (TypeError, ValueError) as error:
                raise UserError(_("La fecha debe tener formato YYYY-MM-DD.")) from error

        params = {}
        if date:
            params["date"] = date
        if marketplace:
            params["marketplace"] = marketplace
        if status:
            params["status"] = status
        if source:
            params["source"] = str(source).strip()[:120]

        try:
            response = requests.get(
                "%s/analytics" % self._api_base_url(),
                headers=self._api_headers(),
                params=params,
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando métricas: %s") % error) from error
        except ValueError as error:
            raise UserError(_("El servicio de métricas no devolvió JSON válido.")) from error

        if not isinstance(payload, dict):
            raise UserError(_("El servicio de métricas devolvió una respuesta inválida."))
        return payload

    @api.model
    def _prepare_values(self, item):
        action_id = self._payload_value(item, "actionId", "action_id", "id")
        change_type = self._payload_value(item, "changeType", "change_type", "type")
        old_value = self._payload_value(item, "oldValue", "old_value")
        new_value = self._payload_value(item, "newValue", "new_value")
        summary = self._build_summary(change_type, old_value, new_value) or self._payload_value(
            item, "summary", "message", "description", "reason"
        )
        return {
            "action_id": str(action_id) if action_id is not None else False,
            "sku": self._payload_value(item, "sku"),
            "marketplace": self._payload_value(item, "marketplace"),
            "status": self._payload_value(item, "status"),
            "change_type": change_type,
            "summary": summary,
            "old_value_json": json.dumps(old_value, ensure_ascii=False, indent=2) if old_value is not None else False,
            "new_value_json": json.dumps(new_value, ensure_ascii=False, indent=2) if new_value is not None else False,
            "error_message": self._payload_value(item, "errorMessage", "error_message", "error"),
            "external_created_at": self._parse_datetime(self._payload_value(item, "createdAt", "created_at")),
            "external_updated_at": self._parse_datetime(self._payload_value(item, "updatedAt", "updated_at")),
            "synced_at": fields.Datetime.now(),
            "payload_json": json.dumps(item, ensure_ascii=False, indent=2),
        }

    @api.model
    def _database_columns(self):
        """Return real columns so a pending module upgrade cannot break the panel."""
        self.env.cr.execute(
            """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND table_name = %s
            """,
            [self._table],
        )
        return {row[0] for row in self.env.cr.fetchall()}

    @api.model
    def _persistable_values(self, values, columns=None):
        columns = columns or self._database_columns()
        return {key: value for key, value in values.items() if key in columns}

    @api.model
    def _item_for_panel(self, values, record_id):
        return {
            "id": record_id,
            "action_id": values.get("action_id"),
            "sku": values.get("sku"),
            "marketplace": values.get("marketplace"),
            "status": values.get("status"),
            "change_type": values.get("change_type"),
            "summary": values.get("summary"),
            "error_message": values.get("error_message"),
            "created_at": values.get("external_created_at"),
            "updated_at": values.get("external_updated_at"),
            "old_value": values.get("old_value_json"),
            "new_value": values.get("new_value_json"),
        }

    @api.model
    def get_changes_page(self, limit=24, offset=0, sku=None, marketplace=None, status=None):
        payload = self._fetch_page(limit, offset, sku=sku, marketplace=marketplace, status=status)
        items = payload.get("items") or []
        panel_items = []
        columns = self._database_columns()
        for item in items:
            values = self._prepare_values(item)
            if not values["action_id"]:
                continue
            existing = self.search([("action_id", "=", values["action_id"])], limit=1)
            persistable_values = self._persistable_values(values, columns=columns)
            if existing:
                existing.write(persistable_values)
                record = existing
            else:
                record = self.create(persistable_values)
            panel_items.append(self._item_for_panel(values, record.id))
        pagination = payload.get("pagination") or {}
        return {
            "items": panel_items,
            "pagination": {
                "limit": int(pagination.get("limit") or limit),
                "offset": int(pagination.get("offset") or offset),
                "total": int(pagination.get("total") or len(panel_items)),
            },
        }

    def _change_item(self):
        self.ensure_one()
        return {
            "id": self.id,
            "action_id": self.action_id,
            "sku": self.sku,
            "marketplace": self.marketplace,
            "status": self.status,
            "change_type": self.change_type,
            "summary": self.summary,
            "error_message": self.error_message,
            "created_at": self.external_created_at,
            "updated_at": self.external_updated_at,
        }

    @api.model
    def action_sync_all(self):
        limit = 100
        offset = 0
        synced_count = 0
        columns = self._database_columns()

        while True:
            payload = self._fetch_page(limit, offset)
            items = payload.get("items") or []
            for item in items:
                values = self._prepare_values(item)
                if not values["action_id"]:
                    continue
                existing = self.search([("action_id", "=", values["action_id"])], limit=1)
                persistable_values = self._persistable_values(values, columns=columns)
                if existing:
                    existing.write(persistable_values)
                else:
                    self.create(persistable_values)
                synced_count += 1

            pagination = payload.get("pagination") or {}
            total = int(pagination.get("total") or 0)
            offset += limit
            if not items or (total and offset >= total):
                break

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Actualizador"),
                "message": _("Cambios sincronizados: %s") % synced_count,
                "type": "success",
                "sticky": False,
            },
        }

    def action_fetch_detail(self):
        self.ensure_one()
        try:
            response = requests.get(
                "%s/%s" % (self._api_base_url(), self.action_id),
                headers=self._api_headers(),
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando el detalle: %s") % error) from error
        except ValueError as error:
            raise UserError(_("El servicio de cambios no devolvió JSON válido.")) from error
        self.write(
            {
                "detail_json": json.dumps(payload, ensure_ascii=False, indent=2),
                "status": self._payload_value(payload, "status", default=self.status),
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Actualizador"),
                "message": _("Detalle actualizado."),
                "type": "success",
                "sticky": False,
            },
        }
