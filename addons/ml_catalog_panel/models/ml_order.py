import json
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MlOrder(models.Model):
    _name = "ml.order"
    _description = "MercadoLibre Order"
    _order = "date_created desc, id desc"

    external_id = fields.Char(string="ID orden", required=True, index=True)
    account_id = fields.Many2one("ml.account", string="Cuenta", ondelete="set null", index=True)
    seller_id = fields.Char(string="Seller ID", index=True)
    buyer_nickname = fields.Char(string="Comprador", index=True)
    status = fields.Char(string="Estado", index=True)
    total_amount = fields.Float(string="Total")
    paid_amount = fields.Float(string="Pagado")
    currency_id = fields.Char(string="Moneda")
    date_created = fields.Datetime(string="Creada en", index=True)
    date_closed = fields.Datetime(string="Cerrada en")
    item_count = fields.Integer(string="Items")
    payload_json = fields.Text(string="Payload completo JSON")

    _sql_constraints = [
        (
            "external_id_unique",
            "unique(external_id)",
            "La orden de MercadoLibre ya existe.",
        )
    ]

    @api.model
    def _to_float(self, value):
        if value in (None, ""):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _to_datetime(self, value):
        if not value:
            return False
        try:
            dt_value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
        if dt_value.tzinfo:
            dt_value = dt_value.astimezone(timezone.utc).replace(tzinfo=None)
        return fields.Datetime.to_string(dt_value)

    @api.model
    def _prepare_order_values(self, order, account):
        buyer = order.get("buyer") or {}
        order_items = order.get("order_items") or []
        return {
            "external_id": str(order.get("id")),
            "account_id": account.id,
            "seller_id": str(account.seller_id or ""),
            "buyer_nickname": buyer.get("nickname"),
            "status": order.get("status"),
            "total_amount": self._to_float(order.get("total_amount")),
            "paid_amount": self._to_float(order.get("paid_amount")),
            "currency_id": order.get("currency_id"),
            "date_created": self._to_datetime(order.get("date_created")),
            "date_closed": self._to_datetime(order.get("date_closed")),
            "item_count": len(order_items),
            "payload_json": json.dumps(order, ensure_ascii=False, indent=2),
        }

    @api.model
    def action_sync_orders(self):
        account = self.env["ml.account"]._get_connected_account()
        if not account.seller_id:
            raise UserError(_("La cuenta conectada no tiene Seller ID."))

        payload = account._api_get(
            "/orders/search",
            params={
                "seller": account.seller_id,
                "sort": "date_desc",
                "limit": 50,
            },
        )
        orders = payload.get("results") or []
        created_count = 0
        updated_count = 0

        for order in orders:
            if not order.get("id"):
                continue
            values = self._prepare_order_values(order, account)
            existing = self.search([("external_id", "=", values["external_id"])], limit=1)
            if existing:
                existing.write(values)
                updated_count += 1
            else:
                self.create(values)
                created_count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("MercadoLibre"),
                "message": _("Ordenes sincronizadas. Creadas: %(created)s. Actualizadas: %(updated)s.")
                % {"created": created_count, "updated": updated_count},
                "type": "success",
                "sticky": False,
            },
        }
