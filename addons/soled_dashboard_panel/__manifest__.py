{
    "name": "SOLED Dashboard Panel",
    "summary": "Vista inicial de modulos operativos SOLED",
    "version": "16.0.1.0.0",
    "category": "Sales",
    "author": "SOLED",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "ml_catalog_panel",
        "retailer_marketplace_panel",
        "sku_publisher_panel",
        "coresa_panel",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/soled_dashboard_views.xml",
        "views/soled_dashboard_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "soled_dashboard_panel/static/src/scss/soled_dashboard_panel.scss",
        ],
    },
    "application": True,
    "installable": True,
}
