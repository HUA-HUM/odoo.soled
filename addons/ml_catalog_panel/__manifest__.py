{
    "name": "MercadoLibre Catalog Panel",
    "summary": "Panel operativo para visualizar productos de MercadoLibre",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "SOLED",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/ml_account_views.xml",
        "views/ml_order_views.xml",
        "views/ml_catalog_views.xml",
        "views/ml_catalog_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ml_catalog_panel/static/src/scss/ml_catalog_panel.scss",
            "ml_catalog_panel/static/src/js/ml_catalog_list_controller.js",
            "ml_catalog_panel/static/src/xml/ml_catalog_list_buttons.xml",
        ],
    },
    "application": True,
    "installable": True,
}
