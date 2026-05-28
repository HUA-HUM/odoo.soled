from odoo import http
from odoo.http import request


class MlOAuthController(http.Controller):
    @http.route("/ml_catalog_panel/oauth/callback", type="http", auth="public", csrf=False)
    def oauth_callback(self, **params):
        code = params.get("code")
        state = params.get("state")
        error = params.get("error")

        if error:
            return request.render(
                "ml_catalog_panel.oauth_result",
                {"title": "Error MercadoLibre", "message": params.get("error_description") or error},
            )

        if not code or not state:
            return request.render(
                "ml_catalog_panel.oauth_result",
                {"title": "Error MercadoLibre", "message": "Faltan parametros code/state en el callback."},
            )

        account = request.env["ml.account"].sudo().search([("state", "=", state)], limit=1)
        if not account:
            return request.render(
                "ml_catalog_panel.oauth_result",
                {"title": "Error MercadoLibre", "message": "No se encontro una cuenta Odoo para este state."},
            )

        try:
            account._exchange_code(code)
        except Exception as error:
            return request.render(
                "ml_catalog_panel.oauth_result",
                {"title": "Error MercadoLibre", "message": str(error)},
            )

        return request.render(
            "ml_catalog_panel.oauth_result",
            {
                "title": "MercadoLibre conectado",
                "message": "La cuenta fue conectada correctamente. Ya podes volver a Odoo.",
            },
        )
