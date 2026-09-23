{
    "name": "Coresa MercadoLibre Publisher",
    "summary": "Publica productos del catalogo Coresa en MercadoLibre",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "author": "SOLED",
    "license": "LGPL-3",
    # coresa_panel se suma a base/web porque los menus cuelgan de su raiz
    # "Coresa" en vez de crear un menu de primer nivel propio.
    "depends": ["base", "web", "coresa_panel"],
    "data": [
        "security/ir.model.access.csv",
        "views/coresa_publication_views.xml",
        "views/coresa_publication_wizard_views.xml",
        "views/coresa_publisher_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "coresa_meli_publisher/static/src/scss/coresa_meli_publisher.scss",
            "coresa_meli_publisher/static/src/js/coresa_publications_action.js",
            "coresa_meli_publisher/static/src/xml/coresa_publications_action.xml",
        ],
    },
    "application": False,
    "installable": True,
}
