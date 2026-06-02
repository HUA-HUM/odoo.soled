import json
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RetailerMarketplaceOrder(models.Model):
    _name = "retailer.marketplace.order"
    _description = "Retailer Marketplace Order"
    _order = "order_date desc, id desc"

    marketplace = fields.Selection(
        [("oncity", "OnCity"), ("fravega", "Fravega")],
        required=True,
        index=True,
    )
    order_id = fields.Char(string="Orden", required=True, index=True)
    suborder_id = fields.Char(string="Suborden", index=True)
    order_date = fields.Datetime(string="Fecha orden", index=True)
    customer_name = fields.Char(string="Cliente", index=True)
    amount = fields.Float(string="Monto")
    status = fields.Char(string="Estado", index=True)
    delivery_status = fields.Char(string="Estado envio", index=True)
    delivery_type = fields.Char(string="Tipo envio")
    items_quantity = fields.Integer(string="Cantidad items")
    products_summary = fields.Text(string="Productos")
    payload_json = fields.Text(string="Payload listado JSON")
    detail_json = fields.Text(string="Detalle JSON")
    synced_at = fields.Datetime(string="Sincronizado en")
    detail_synced_at = fields.Datetime(string="Detalle sincronizado en")

    _sql_constraints = [
        ("marketplace_order_unique", "unique(marketplace, order_id, suborder_id)", "La orden del marketplace ya existe."),
    ]

    @api.model
    def _api_base_url(self):
        return "https://marketplace.api.solediluminacion.com"

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
        return json.dumps(value if value is not None else {}, ensure_ascii=False, indent=2)

    @api.model
    def _parse_datetime(self, value):
        if not value:
            return False
        return str(value).replace("T", " ").replace("Z", "").split(".")[0][:19]

    @api.model
    def _products_summary(self, products):
        lines = []
        for product in products or []:
            sku = product.get("sellerSku") or product.get("sku") or ""
            name = product.get("name") or product.get("title") or ""
            quantity = product.get("quantity") or ""
            lines.append("%s x%s %s" % (sku, quantity, name))
        return "\n".join(lines)

    @api.model
    def _upsert_order(self, values):
        domain = [
            ("marketplace", "=", values["marketplace"]),
            ("order_id", "=", values["order_id"]),
            ("suborder_id", "=", values.get("suborder_id") or False),
        ]
        existing = self.search(domain, limit=1)
        if existing:
            existing.write(values)
            return "updated"
        self.create(values)
        return "created"

    @api.model
    def _prepare_oncity_order_values(self, order):
        customer = order.get("Cliente") or {}
        statuses = order.get("Estado") or []
        last_status = statuses[-1] if statuses else {}
        products = order.get("Productos") or []
        return {
            "marketplace": "oncity",
            "order_id": str(order.get("IdOrden") or ""),
            "suborder_id": False,
            "order_date": self._parse_datetime(order.get("Fecha")),
            "customer_name": ("%s %s" % (customer.get("Nombre") or "", customer.get("Apellido") or "")).strip(),
            "amount": self._to_float(order.get("MontoVenta")),
            "status": last_status.get("Descripcion"),
            "delivery_status": False,
            "delivery_type": False,
            "items_quantity": len(products),
            "products_summary": self._products_summary(products),
            "payload_json": self._to_json(order),
            "synced_at": fields.Datetime.now(),
        }

    @api.model
    def _prepare_fravega_order_values(self, order):
        products = order.get("products") or []
        return {
            "marketplace": "fravega",
            "order_id": str(order.get("orderId") or ""),
            "suborder_id": order.get("suborderId") or False,
            "order_date": self._parse_datetime(order.get("purchaseDate") or order.get("createdOn")),
            "customer_name": order.get("clientName"),
            "amount": self._to_float(order.get("amount")),
            "status": order.get("status"),
            "delivery_status": order.get("deliveryStatus"),
            "delivery_type": ", ".join(order.get("deliveryType") or []),
            "items_quantity": self._to_int(order.get("itemsQuantity")) or len(products),
            "products_summary": self._products_summary(products),
            "payload_json": self._to_json(order),
            "synced_at": fields.Datetime.now(),
        }

    @api.model
    def action_sync_oncity_orders(self):
        now = datetime.utcnow()
        start = now - timedelta(days=90)
        try:
            response = requests.get(
                "%s/oncity/orders" % self._api_base_url(),
                headers={"accept": "*/*"},
                params={
                    "fechaDesde": start.strftime("%Y-%m-%dT00:00:00.000Z"),
                    "fechaHasta": now.strftime("%Y-%m-%dT23:59:59.999Z"),
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando ordenes OnCity: %s") % error) from error
        except ValueError as error:
            raise UserError(_("OnCity no devolvio JSON valido.")) from error

        orders = payload if isinstance(payload, list) else payload.get("items") or payload.get("data") or []
        counts = {"created": 0, "updated": 0}
        for order in orders:
            if not order.get("IdOrden"):
                continue
            counts[self._upsert_order(self._prepare_oncity_order_values(order))] += 1
        return self._notification("OnCity", _("Ordenes OnCity sincronizadas. Creadas: %(created)s. Actualizadas: %(updated)s.") % counts)

    @api.model
    def action_sync_fravega_orders(self):
        page = 1
        page_size = 100
        counts = {"created": 0, "updated": 0}
        while True:
            try:
                response = requests.get(
                    "%s/fravega/orders" % self._api_base_url(),
                    headers={"accept": "*/*"},
                    params={"page": page, "page-size": page_size},
                    timeout=60,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as error:
                raise UserError(_("Error consultando ordenes Fravega: %s") % error) from error
            except ValueError as error:
                raise UserError(_("Fravega no devolvio JSON valido.")) from error

            orders = payload.get("items") or []
            for order in orders:
                if not order.get("orderId"):
                    continue
                counts[self._upsert_order(self._prepare_fravega_order_values(order))] += 1

            pages = self._to_int(payload.get("pages")) or page
            if page >= pages or not orders:
                break
            page += 1
        return self._notification("Fravega", _("Ordenes Fravega sincronizadas. Creadas: %(created)s. Actualizadas: %(updated)s.") % counts)

    def action_fetch_fravega_detail(self):
        self.ensure_one()
        if self.marketplace != "fravega":
            raise UserError(_("El detalle por ahora esta disponible para Fravega."))
        if not self.suborder_id or not self.order_id:
            raise UserError(_("La orden no tiene orderId/suborderId."))
        try:
            response = requests.get(
                "%s/fravega/orders/%s" % (self._api_base_url(), self.suborder_id),
                headers={"accept": "*/*"},
                params={"orderid": self.order_id},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise UserError(_("Error consultando detalle Fravega: %s") % error) from error
        except ValueError as error:
            raise UserError(_("Fravega no devolvio JSON valido.")) from error
        self.write({"detail_json": self._to_json(payload), "detail_synced_at": fields.Datetime.now()})
        return self._notification("Fravega", _("Detalle de orden actualizado."))

    def _notification(self, title, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }
