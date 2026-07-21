{
    "name": "SKU Publisher Panel",
    "summary": "Publicador operativo de SKUs hacia marketplaces",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "SOLED",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
        "ml_catalog_panel",
        "retailer_marketplace_panel",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/publisher_sku_search_wizard_views.xml",
        "views/publisher_sku_views.xml",
        "views/publisher_job_views.xml",
        "views/publisher_dashboard_views.xml",
        "views/publisher_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sku_publisher_panel/static/src/scss/sku_publisher_panel.scss",
            "sku_publisher_panel/static/src/js/publisher_list_controller.js",
            "sku_publisher_panel/static/src/js/publisher_candidates_action.js",
            "sku_publisher_panel/static/src/xml/publisher_list_buttons.xml",
            "sku_publisher_panel/static/src/xml/publisher_candidates_action.xml",
        ],
    },
    "application": True,
    "installable": True,
}
