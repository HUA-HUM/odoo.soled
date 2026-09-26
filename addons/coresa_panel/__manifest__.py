{
    "name": "Coresa Panel",
    "summary": "Panel operativo para Coresa",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "SOLED",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/coresa_dashboard_views.xml",
        "views/coresa_updater_views.xml",
        "views/coresa_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "coresa_panel/static/src/scss/coresa_panel.scss",
            "coresa_panel/static/src/js/coresa_catalog_action.js",
            "coresa_panel/static/src/xml/coresa_catalog_action.xml",
            "coresa_panel/static/src/js/coresa_updater_action.js",
            "coresa_panel/static/src/xml/coresa_updater_action.xml",
        ],
    },
    "application": True,
    "installable": True,
}
