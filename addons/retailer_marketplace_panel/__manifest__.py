{
    "name": "Retailer Marketplace Panel",
    "summary": "Panel operativo de retailers y marketplaces",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "SOLED",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/retailer_marketplace_views.xml",
        "views/oncity_product_views.xml",
        "views/fravega_product_views.xml",
        "views/marketplace_order_views.xml",
        "views/retailer_marketplace_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "retailer_marketplace_panel/static/src/scss/retailer_marketplace_panel.scss",
            "retailer_marketplace_panel/static/src/js/oncity_list_controller.js",
            "retailer_marketplace_panel/static/src/xml/oncity_list_buttons.xml",
        ],
    },
    "application": True,
    "installable": True,
}
