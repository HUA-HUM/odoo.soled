from odoo.addons.web.controllers.webmanifest import WebManifest


class SoledWebManifest(WebManifest):
    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        manifest["name"] = "SOLED"
        manifest["background_color"] = "#16202c"
        manifest["theme_color"] = "#16202c"
        manifest["icons"] = [
            {
                "src": "/soled_dashboard_panel/static/src/img/soled_app_icon_192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "/soled_dashboard_panel/static/src/img/soled_app_icon_512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ]
        return manifest

    def _icon_path(self):
        return "soled_dashboard_panel/static/src/img/soled_app_icon_192.png"
