import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MlAccount(models.Model):
    _name = "ml.account"
    _description = "MercadoLibre Account"
    _order = "id desc"

    name = fields.Char(default="Cuenta MercadoLibre", required=True)
    app_id = fields.Char(string="App ID / Client ID", required=True)
    client_secret = fields.Char(string="Client Secret", required=True)
    redirect_uri = fields.Char(string="Redirect URI", required=True)
    state = fields.Char(readonly=True)
    connected = fields.Boolean(readonly=True)
    seller_id = fields.Char(string="Seller ID", readonly=True)
    nickname = fields.Char(readonly=True)
    access_token = fields.Char(readonly=True)
    refresh_token = fields.Char(readonly=True)
    token_expires_at = fields.Datetime(readonly=True)
    last_connection_at = fields.Datetime(readonly=True)
    product_count = fields.Integer(string="Productos", compute="_compute_dashboard_counts")
    active_product_count = fields.Integer(string="Productos activos", compute="_compute_dashboard_counts")
    paused_product_count = fields.Integer(string="Productos pausados", compute="_compute_dashboard_counts")
    order_count = fields.Integer(string="Ordenes", compute="_compute_dashboard_counts")
    last_order_at = fields.Datetime(string="Ultima orden", compute="_compute_dashboard_counts")

    @api.depends("seller_id")
    def _compute_dashboard_counts(self):
        Product = self.env["ml.product"]
        Order = self.env["ml.order"]
        for account in self:
            product_domain = []
            if account.seller_id:
                product_domain = [("seller_id", "=", str(account.seller_id))]
            order_domain = []
            if account.seller_id:
                order_domain = [("seller_id", "=", str(account.seller_id))]

            account.product_count = Product.search_count(product_domain)
            account.active_product_count = Product.search_count(product_domain + [("status", "=", "active")])
            account.paused_product_count = Product.search_count(product_domain + [("status", "=", "paused")])
            account.order_count = Order.search_count(order_domain)
            last_order = Order.search(order_domain, order="date_created desc", limit=1)
            account.last_order_at = last_order.date_created if last_order else False

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "redirect_uri" in fields_list and not values.get("redirect_uri"):
            values["redirect_uri"] = "%s/ml_catalog_panel/oauth/callback" % self.env["ir.config_parameter"].sudo().get_param(
                "web.base.url", "http://localhost:8069"
            )
        return values

    def _ensure_credentials(self):
        self.ensure_one()
        if not self.app_id or not self.client_secret or not self.redirect_uri:
            raise UserError(_("Completa App ID, Client Secret y Redirect URI antes de conectar."))

    @api.model
    def _get_connected_account(self):
        account = self.search([("connected", "=", True), ("access_token", "!=", False)], limit=1)
        if not account:
            raise UserError(_("Primero conecta una cuenta de MercadoLibre desde Configuracion > Cuenta."))
        return account

    def action_connect(self):
        self.ensure_one()
        self._ensure_credentials()
        state = secrets.token_urlsafe(24)
        self.write({"state": state})
        params = urlencode(
            {
                "response_type": "code",
                "client_id": self.app_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "https://auth.mercadolibre.com.ar/authorization?%s" % params,
            "target": "self",
        }

    def _exchange_code(self, code):
        self.ensure_one()
        self._ensure_credentials()
        response = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.app_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )
        self._apply_token_response(response)

    def action_refresh_token(self):
        self.ensure_one()
        if not self.refresh_token:
            raise UserError(_("Todavia no hay refresh token. Conecta la cuenta primero."))
        response = requests.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.app_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )
        self._apply_token_response(response)
        return self._notification(_("Token actualizado correctamente."), "success")

    def _api_get(self, path, params=None):
        self.ensure_one()
        if not self.access_token:
            raise UserError(_("Todavia no hay access token. Conecta la cuenta primero."))
        if self.token_expires_at and self.token_expires_at <= fields.Datetime.now() + timedelta(minutes=5):
            self.action_refresh_token()

        response = requests.get(
            "https://api.mercadolibre.com%s" % path,
            headers={
                "accept": "application/json",
                "Authorization": "Bearer %s" % self.access_token,
            },
            params=params or {},
            timeout=45,
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise UserError(_("MercadoLibre no devolvio JSON valido: %s") % response.text) from error

        if response.status_code >= 400:
            raise UserError(_("Error consultando MercadoLibre: %s") % payload)
        return payload

    def action_open_catalog(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Catalogo MercadoLibre"),
            "res_model": "ml.product",
            "view_mode": "list,form",
        }

    def action_open_orders(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Ordenes MercadoLibre"),
            "res_model": "ml.order",
            "view_mode": "list,form",
        }

    def _apply_token_response(self, response):
        self.ensure_one()
        try:
            payload = response.json()
        except ValueError as error:
            raise UserError(_("MercadoLibre no devolvio JSON valido: %s") % response.text) from error

        if response.status_code >= 400:
            raise UserError(_("Error OAuth MercadoLibre: %s") % payload)

        expires_in = int(payload.get("expires_in") or 0)
        expires_at = fields.Datetime.now() + timedelta(seconds=expires_in) if expires_in else False
        self.write(
            {
                "access_token": payload.get("access_token"),
                "refresh_token": payload.get("refresh_token") or self.refresh_token,
                "seller_id": payload.get("user_id"),
                "token_expires_at": expires_at,
                "connected": True,
                "last_connection_at": fields.Datetime.now(),
            }
        )
        self.action_test_connection(show_notification=False)

    def action_test_connection(self, show_notification=True):
        self.ensure_one()
        if not self.access_token:
            raise UserError(_("Todavia no hay access token. Conecta la cuenta primero."))
        response = requests.get(
            "https://api.mercadolibre.com/users/me",
            headers={"Authorization": "Bearer %s" % self.access_token},
            timeout=30,
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise UserError(_("MercadoLibre no devolvio JSON valido: %s") % response.text) from error

        if response.status_code >= 400:
            raise UserError(_("No se pudo validar la cuenta MercadoLibre: %s") % payload)

        self.write(
            {
                "seller_id": payload.get("id") or self.seller_id,
                "nickname": payload.get("nickname"),
                "last_connection_at": fields.Datetime.now(),
            }
        )
        if show_notification:
            return self._notification(_("Cuenta MercadoLibre conectada: %s") % (payload.get("nickname") or payload.get("id")), "success")
        return True

    def _notification(self, message, notification_type):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("MercadoLibre"),
                "message": message,
                "type": notification_type,
                "sticky": False,
            },
        }
