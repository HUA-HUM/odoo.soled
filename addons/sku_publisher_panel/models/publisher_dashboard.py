import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PublisherDashboard(models.Model):
    _name = "publisher.dashboard"
    _description = "SKU Publisher Dashboard"

    name = fields.Char(default="Dashboard")
    candidate_count = fields.Integer(compute="_compute_counts")
    job_count = fields.Integer(compute="_compute_counts")
    run_count = fields.Integer(compute="_compute_counts")

    @api.depends()
    def _compute_counts(self):
        sku_model = self.env["publisher.sku"]
        job_model = self.env["publisher.job"]
        run_model = self.env["publisher.job.line"]
        for dashboard in self:
            dashboard.candidate_count = sku_model.search_count([])
            dashboard.job_count = job_model.search_count([])
            dashboard.run_count = run_model.search_count([])

    # ------------------------------------------------------------------
    # Resumen en vivo
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_overview(self):
        """Numeros del dashboard leidos de las APIs.

        Antes salian de las tablas locales, que solo se llenan al apretar los
        botones de sincronizar: al entrar se veian tres ceros.
        """
        return {
            "candidates": self._overview_candidates(),
            "jobs": self._overview_jobs(),
        }

    @api.model
    def _overview_candidates(self):
        sku_model = self.env["publisher.sku"]
        try:
            facets = sku_model.get_candidate_filters()
        except Exception as error:  # noqa: BLE001 - el dashboard no debe romperse
            _logger.warning("Publicador: no se pudieron leer los filtros: %s", error)
            return {"error": _("No se pudo consultar la API de candidatos.")}

        def totals_by_value(rows):
            return {
                row.get("value"): self._as_count(row.get("total"))
                for row in (rows or [])
                if isinstance(row, dict)
            }

        stock = totals_by_value(facets.get("stock"))
        statuses = totals_by_value(facets.get("statuses"))
        listing_types = totals_by_value(facets.get("listingTypes"))
        marketplaces = facets.get("marketplaces") or ["oncity", "fravega"]

        pending = []
        for marketplace in marketplaces:
            total = self._pending_for_marketplace(sku_model, marketplace)
            if total is not None:
                pending.append({"marketplace": marketplace, "total": total})

        return {
            "total": self._as_count(facets.get("total")),
            "in_stock": stock.get("in_stock", 0),
            "active": statuses.get("active", 0),
            "premium": listing_types.get("cuotas", 0),
            "pending": pending,
        }

    @api.model
    def _pending_for_marketplace(self, sku_model, marketplace):
        try:
            payload = sku_model._fetch_publication_status(
                limit=1, offset=0, filters={"notPublishedIn": marketplace}
            )
        except Exception as error:  # noqa: BLE001
            _logger.warning("Publicador: pendientes de %s fallo: %s", marketplace, error)
            return None
        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        return self._as_count((pagination or {}).get("total"))

    @api.model
    def _overview_jobs(self):
        job_model = self.env["publisher.job"]
        items = []
        total = 0
        offset = 0
        # Recorremos todas las paginas para que los agregados sean exactos y no
        # solo de los ultimos 100 procesos.
        for _page in range(5):
            try:
                payload = job_model._api_request(
                    "GET", "/publisher/jobs", params={"limit": 100, "offset": offset}
                )
            except Exception as error:  # noqa: BLE001
                _logger.warning("Publicador: no se pudieron leer los procesos: %s", error)
                if items:
                    break
                return {"error": _("No se pudo consultar products.api.")}
            page_items = payload.get("items") or []
            items.extend(item for item in page_items if isinstance(item, dict))
            pagination = payload.get("pagination") or {}
            total = self._as_count(pagination.get("total")) or len(items)
            offset += 100
            if not page_items or offset >= total:
                break

        counters = {
            "items": 0,
            "done": 0,
            "error": 0,
            "queued": 0,
            "processing": 0,
            "skipped": 0,
        }
        by_status = {}
        for job in items:
            counters["items"] += self._as_count(job.get("total_items"))
            counters["done"] += self._as_count(job.get("done_items"))
            counters["error"] += self._as_count(job.get("error_items"))
            counters["queued"] += self._as_count(job.get("queued_items"))
            counters["processing"] += self._as_count(job.get("processing_items"))
            counters["skipped"] += self._as_count(job.get("skipped_items"))
            status = (job.get("status") or "unknown").strip()
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total": total,
            "counters": counters,
            "by_status": by_status,
            "recent": [self._job_summary(job) for job in items[:6]],
        }

    @api.model
    def _job_summary(self, job):
        request = job.get("original_request")
        request = request if isinstance(request, dict) else {}
        marketplaces = request.get("marketplaces")
        return {
            "job_id": job.get("job_id") or "",
            "status": job.get("status") or "",
            "requested_by": job.get("requested_by_name") or "",
            "marketplaces": marketplaces if isinstance(marketplaces, list) else [],
            "total": self._as_count(job.get("total_items")),
            "done": self._as_count(job.get("done_items")),
            "error": self._as_count(job.get("error_items")),
            "created_at": job.get("created_at") or "",
            "finished_at": job.get("finished_at") or "",
        }

    @api.model
    def _as_count(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_open_candidates(self):
        return self.env.ref("sku_publisher_panel.action_publisher_candidates_cards").read()[0]

    def action_refresh_candidates(self):
        return self.env["publisher.sku"].action_refresh_candidates()

    def action_open_jobs(self):
        return self.env.ref("sku_publisher_panel.action_publisher_job").read()[0]

    def action_sync_recent_jobs(self):
        return self.env["publisher.job"].action_sync_recent_jobs()

    def action_open_runs(self):
        return self.env.ref("sku_publisher_panel.action_publisher_run").read()[0]

    def action_sync_runs(self):
        return self.env["publisher.job.line"].action_sync_runs()
