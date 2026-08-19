{
    "name": "SOLED Dashboard Panel",
    "summary": "Vista inicial de modulos operativos SOLED",
    "version": "18.0.1.1.0",
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
        "data/company_logo.xml",
        "views/soled_favicon_templates.xml",
        "views/soled_dashboard_views.xml",
        "views/soled_dashboard_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "soled_dashboard_panel/static/src/scss/soled_dashboard_panel.scss",
            "soled_dashboard_panel/static/src/js/soled_global_sidebar.js",
            "soled_dashboard_panel/static/src/xml/soled_global_sidebar.xml",
        ],
    },
    "application": True,
    "installable": True,
}
