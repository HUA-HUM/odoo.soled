{
    "name": "Coresa Panel",
    "summary": "Panel operativo para Coresa",
    "version": "16.0.1.0.0",
    "category": "Sales",
    "author": "SOLED",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/coresa_dashboard_views.xml",
        "views/coresa_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "coresa_panel/static/src/scss/coresa_panel.scss",
        ],
    },
    "application": True,
    "installable": True,
}
