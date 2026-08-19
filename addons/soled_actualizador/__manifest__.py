{
    'name': 'Soled - Actualizador de Marketplaces',
    # Ajustá el "17" inicial a tu version real de Odoo si es distinta.
    'version': '17.0.1.0.0',
    'summary': 'Panel de seguimiento de cambios de precio/stock/estado propagados a Fravega y OnCity',
    'description': """
Sincroniza y muestra en Odoo el historial de cambios de precio, stock y
estado que products.api propaga hacia los marketplaces (Fravega, OnCity),
leyendo desde el endpoint interno de internal-soled
(GET /internal/marketplace-change-actions), que refleja la tabla
marketplace_product_change_actions.

No escribe nada en el catalogo real: es solo un espejo de solo lectura para
seguimiento y diagnostico.
    """,
    'author': 'Soled',
    'category': 'Retailer/Actualizador',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/marketplace_change_action_views.xml',
        'views/marketplace_change_action_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'soled_actualizador/static/src/scss/soled_actualizador.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
