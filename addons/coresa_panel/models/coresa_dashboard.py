import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CoresaDashboard(models.Model):
    """Portada del modulo Coresa.

    Los numeros salen en vivo de la API interna. Cada bloque se pide por
    separado y se traga su propio error: si una parte no responde, la
    portada igual abre y las demas secciones siguen siendo navegables.
    """

    _name = "coresa.dashboard"
    _description = "Coresa Dashboard"

    name = fields.Char(default="Coresa")

    # Las dos ultimas viven en coresa_meli_publisher, que no es dependencia:
    # se resuelven en caliente y, si el modulo no esta, la tarjeta no se
    # muestra en vez de romper la portada.
    SECTIONS = [
        {
            "key": "catalog",
            "label": "Catálogo",
            "icon": "fa-th-large",
            "hint": "Todos los productos del mayorista, con ficha técnica y filtros.",
            "action": "coresa_panel.action_coresa_catalog",
        },
        {
            "key": "updater",
            "label": "Actualizador",
            "icon": "fa-refresh",
            "hint": "Lo que está publicado en MercadoLibre y qué sincroniza de cada uno.",
            "action": "coresa_panel.action_coresa_updater",
        },
        {
            "key": "publish",
            "label": "Publicar SKU",
            "icon": "fa-upload",
            "hint": "Arma el borrador de una publicación nueva a partir de un SKU.",
            "action": "coresa_meli_publisher.action_coresa_publication_wizard",
        },
        {
            "key": "publications",
            "label": "Publicaciones",
            "icon": "fa-paper-plane-o",
            "hint": "Borradores, envíos y el resultado de cada publicación.",
            "action": "coresa_meli_publisher.action_coresa_publications_panel",
        },
        {
            "key": "orders",
            "label": "Órdenes",
            "icon": "fa-shopping-cart",
            "hint": "Ventas y seguimiento operativo.",
            "action": None,
        },
        {
            "key": "shipments",
            "label": "Envíos",
            "icon": "fa-truck",
            "hint": "Logística y estados de entrega.",
            "action": None,
        },
        {
            "key": "invoices",
            "label": "Facturación",
            "icon": "fa-file-text-o",
            "hint": "Comprobantes y conciliación.",
            "action": None,
        },
    ]

    PUBLICATIONS_PAGE = 200
    PUBLICATIONS_MAX_PAGES = 5

    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_sections(self):
        """Las tarjetas, sin tocar la API.

        Va en una llamada aparte de los contadores porque esos tardan un
        par de segundos: asi la portada se dibuja entera de entrada y los
        numeros entran despues.
        """
        sections = []
        for section in self.SECTIONS:
            if section["action"] and not self.env.ref(section["action"], raise_if_not_found=False):
                continue
            sections.append(dict(section, available=bool(section["action"])))
        return sections

    @api.model
    def get_dashboard_counters(self):
        catalog = self.env["coresa.catalog"]
        data = {
            "catalog": 0,
            "publications": 0,
            "skus": 0,
            "stock": 0,
            "price": 0,
            "publisher": {"total": 0, "pending": 0, "published": 0, "failed": 0},
            "metrics": {},
            "errors": [],
        }

        try:
            payload = catalog._api_get("/internal/coresa/products", {"limit": 1, "offset": 0})
            data["catalog"] = catalog._as_int(((payload or {}).get("pagination") or {}).get("total"))
        except Exception as error:  # noqa: BLE001 - la portada no se cae por un contador
            _logger.info("Portada Coresa: catalogo sin datos (%s)", error)
            data["errors"].append("No se pudo leer el catálogo.")

        try:
            summary = self.env["coresa.updater"].get_updater_summary()
            data["publications"] = summary.get("total", 0)
            data["skus"] = summary.get("skus", 0)
            data["stock"] = summary.get("stock", 0)
            data["price"] = summary.get("price", 0)
        except Exception as error:  # noqa: BLE001
            _logger.info("Portada Coresa: actualizador sin datos (%s)", error)
            data["errors"].append("No se pudo leer lo publicado en MercadoLibre.")

        try:
            data["publisher"] = self._publisher_counters()
        except Exception as error:  # noqa: BLE001
            _logger.info("Portada Coresa: publicador sin datos (%s)", error)
            data["errors"].append("No se pudo leer el publicador.")

        data["metrics"] = {
            "catalog": self._metric(data["catalog"], "productos"),
            "updater": self._metric(data["publications"], "publicaciones"),
            "publications": self._metric(data["publisher"]["total"], "en el registro"),
        }
        return data

    # ------------------------------------------------------------------
    @api.model
    def _publisher_counters(self):
        """Publicaciones del publicador agrupadas por estado.

        Se cuenta sobre las filas y no con un pedido por estado: son pocas
        y asi es una sola llamada en vez de siete.
        """
        catalog = self.env["coresa.catalog"]
        counters = {"total": 0, "pending": 0, "published": 0, "failed": 0}
        pending = {"draft", "ready", "publishing"}
        offset = 0
        for _page in range(self.PUBLICATIONS_MAX_PAGES):
            payload = catalog._api_get(
                "/internal/coresa/publications",
                {"limit": self.PUBLICATIONS_PAGE, "offset": offset},
            ) or {}
            items = [item for item in ((payload or {}).get("items") or []) if isinstance(item, dict)]
            counters["total"] = catalog._as_int(((payload or {}).get("pagination") or {}).get("total"))
            for item in items:
                status = item.get("status") or ""
                if status in pending:
                    counters["pending"] += 1
                elif status == "published":
                    counters["published"] += 1
                elif status in ("failed", "partial"):
                    counters["failed"] += 1
            offset += len(items)
            if not items or offset >= counters["total"]:
                break
        return counters

    @api.model
    def _metric(self, value, noun):
        if not value:
            return ""
        return "%s %s" % ("{:,}".format(int(value)).replace(",", "."), noun)

    # ------------------------------------------------------------------
    def action_open_catalog(self):
        action = self.env.ref("coresa_panel.action_coresa_catalog", raise_if_not_found=False)
        return action.read()[0] if action else False
