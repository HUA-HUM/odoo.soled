import json
import uuid

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PublisherJob(models.Model):
    _name = "publisher.job"
    _description = "SKU Publisher Job"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    status = fields.Selection(
        [
            ("queued", "En cola"),
            ("processing", "Procesando"),
            ("completed", "Completado"),
            ("completed_with_errors", "Completado con errores"),
            ("failed", "Fallido"),
            ("cancelled", "Cancelado"),
        ],
        default="queued",
        required=True,
        index=True,
    )
    retailer_targets = fields.Char(string="Retailers")
    progress = fields.Integer(default=0)
    total_items = fields.Integer()
    done_items = fields.Integer()
    error_items = fields.Integer()
    backend_job_id = fields.Char(string="Job backend")
    message = fields.Text()
    line_ids = fields.One2many("publisher.job.line", "job_id", string="Lineas")
    raw_payload_json = fields.Text(string="Payload API")

    @api.model
    def _api_base_url(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "sku_publisher_panel.products_api_base_url",
            "https://api.products.solediluminacion.com",
        ).rstrip("/")

    @api.model
    def _internal_api_base_url(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "sku_publisher_panel.internal_api_base_url",
            "https://internal.solediluminacion.com",
        ).rstrip("/")

    @api.model
    def _internal_api_key(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "sku_publisher_panel.internal_api_key",
            "_internal",
        )

    @api.model
    def _api_request(self, method, path, **kwargs):
        url = "%s%s" % (self._api_base_url(), path)
        try:
            response = requests.request(method, url, timeout=45, **kwargs)
        except requests.RequestException as error:
            raise UserError(_("No se pudo conectar con products.api: %s") % error) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise UserError(_("products.api no devolvio JSON valido: %s") % response.text) from error

        if response.status_code >= 400:
            raise UserError(_("Error products.api: %s") % payload)
        return payload

    @api.model
    def _internal_api_request(self, method, path, **kwargs):
        url = "%s%s" % (self._internal_api_base_url(), path)
        headers = kwargs.pop("headers", {})
        headers.update(
            {
                "accept": "*/*",
                "x-internal-api-key": self._internal_api_key(),
            }
        )
        try:
            response = requests.request(method, url, timeout=45, headers=headers, **kwargs)
        except requests.RequestException as error:
            raise UserError(_("No se pudo conectar con la API interna: %s") % error) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise UserError(_("La API interna no devolvio JSON valido: %s") % response.text) from error

        if response.status_code >= 400:
            raise UserError(_("Error API interna: %s") % payload)
        return payload

    @api.model
    def _payload_value(self, payload, *keys, default=None):
        for key in keys:
            if key in payload and payload.get(key) is not None:
                return payload.get(key)
        return default

    @api.model
    def create_from_candidates(self, candidates, retailers):
        candidates = candidates.filtered(lambda item: item.ready_to_publish and item.sku)
        if not candidates:
            raise UserError(_("Selecciona SKUs listos para publicar."))

        requested_by = {
            "odooUserId": self.env.user.id,
            "name": self.env.user.name,
            "email": self.env.user.email or "",
        }
        idempotency_key = "odoo-publish-%s" % uuid.uuid4().hex
        request_payload = {
            "source": "mercadolibre",
            "skus": candidates.mapped("sku"),
            "marketplaces": retailers,
            "requestedBy": requested_by,
            "options": {
                "forceRepublish": False,
            },
            "idempotencyKey": idempotency_key,
        }
        payload = self._api_request(
            "POST",
            "/publisher/jobs",
            json=request_payload,
            headers={"Content-Type": "application/json"},
        )
        job = self._upsert_from_payload(payload, candidates_by_sku={candidate.sku: candidate for candidate in candidates})
        job.write(
            {
                "name": _("Publicacion %(job)s") % {"job": self._payload_value(payload, "jobId", "job_id", default=fields.Datetime.now())},
                "retailer_targets": ", ".join(retailers),
                "message": _("Job creado desde Odoo."),
            }
        )
        return job

    @api.model
    def _upsert_from_payload(self, payload, candidates_by_sku=None):
        backend_job_id = self._payload_value(payload, "jobId", "job_id")
        if not backend_job_id:
            raise UserError(_("products.api no devolvio jobId."))

        total_items = int(self._payload_value(payload, "totalItems", "total_items", default=0) or 0)
        done_items = int(self._payload_value(payload, "doneItems", "done_items", default=0) or 0)
        error_items = int(self._payload_value(payload, "errorItems", "error_items", default=0) or 0)
        skipped_items = int(self._payload_value(payload, "skippedItems", "skipped_items", default=0) or 0)
        progress = self._payload_value(payload, "progress")
        if progress is None and total_items:
            progress = int(round(((done_items + error_items + skipped_items) / total_items) * 100))

        original_request = payload.get("original_request") or payload.get("originalRequest") or {}
        marketplaces = original_request.get("marketplaces") or []
        values = {
            "name": _("Publicacion %(job)s") % {"job": backend_job_id},
            "backend_job_id": backend_job_id,
            "status": payload.get("status") or "queued",
            "retailer_targets": ", ".join(marketplaces),
            "progress": int(progress or 0),
            "total_items": total_items,
            "done_items": done_items,
            "error_items": error_items,
            "raw_payload_json": json.dumps(payload, ensure_ascii=False, indent=2),
        }
        job = self.search([("backend_job_id", "=", backend_job_id)], limit=1)
        if job:
            job.write(values)
        else:
            job = self.create(values)

        line_model = self.env["publisher.job.line"]
        candidates_by_sku = candidates_by_sku or {}
        for item in payload.get("items") or []:
            run_id = self._payload_value(item, "runId", "run_id")
            if not run_id:
                continue
            line = line_model.search([("run_id", "=", run_id)], limit=1)
            sku = item.get("sku")
            candidate = candidates_by_sku.get(sku) or self.env["publisher.sku"].search([("sku", "=", sku)], limit=1)
            line_values = {
                "job_id": job.id,
                "sku_id": candidate.id if candidate else False,
                "sku": sku,
                "retailer": item.get("marketplace"),
                "status": item.get("status") or "queued",
                "message": item.get("message"),
                "run_id": run_id,
                "backend_reference": run_id,
            }
            if line:
                line.write(line_values)
            else:
                line_model.create(line_values)
        return job

    def action_refresh_progress(self):
        self.ensure_one()
        if not self.backend_job_id:
            raise UserError(_("Este proceso todavia no tiene jobId backend."))
        payload = self._api_request("GET", "/publisher/jobs/%s" % self.backend_job_id)
        self._upsert_from_payload(payload)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Publicador"),
                "message": _("Progreso actualizado."),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def action_sync_recent_jobs(self):
        payload = self._api_request("GET", "/publisher/jobs", params={"status": "queued", "limit": 50, "offset": 0})
        jobs = payload.get("items") or payload.get("jobs") or payload.get("data") or []
        synced_count = 0
        for job_payload in jobs:
            if self._payload_value(job_payload, "jobId", "job_id"):
                self._upsert_from_payload(job_payload)
                synced_count += 1
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Publicador"),
                "message": _("Procesos sincronizados: %s") % synced_count,
                "type": "success",
                "sticky": False,
            },
        }


class PublisherJobLine(models.Model):
    _name = "publisher.job.line"
    _description = "SKU Publisher Job Line"
    _order = "job_id desc, id"

    job_id = fields.Many2one("publisher.job", required=True, ondelete="cascade")
    sku_id = fields.Many2one("publisher.sku", string="Candidato")
    sku = fields.Char(required=True, index=True)
    retailer = fields.Selection(
        [
            ("oncity", "OnCity"),
            ("fravega", "Fravega"),
        ],
        required=True,
        index=True,
    )
    status = fields.Selection(
        [
            ("queued", "En cola"),
            ("processing", "Procesando"),
            ("retrying", "Reintentando"),
            ("completed", "Completado"),
            ("failed", "Fallido"),
            ("skipped", "Omitido"),
            ("cancelled", "Cancelado"),
        ],
        default="queued",
        required=True,
        index=True,
    )
    message = fields.Text()
    backend_reference = fields.Char()
    run_id = fields.Char(string="Run ID", index=True)
    attempts = fields.Integer()
    max_attempts = fields.Integer()
    error_message = fields.Text()
    error_code = fields.Char()
    marketplace_publication_id = fields.Char()
    external_product_id = fields.Char()
    started_at = fields.Datetime()
    finished_at = fields.Datetime()
    raw_payload_json = fields.Text(string="Payload API")

    @api.model
    def _api_datetime(self, value):
        if not value:
            return False
        return str(value).replace("T", " ").replace("Z", "").split(".")[0]

    @api.model
    def _upsert_from_run_payload(self, payload):
        run_id = payload.get("run_id") or payload.get("runId")
        if not run_id:
            return False

        backend_job_id = payload.get("job_id") or payload.get("jobId")
        job = self.env["publisher.job"].search([("backend_job_id", "=", backend_job_id)], limit=1)
        if not job and backend_job_id:
            job = self.env["publisher.job"].create(
                {
                    "name": _("Publicacion %(job)s") % {"job": backend_job_id},
                    "backend_job_id": backend_job_id,
                    "status": "queued",
                    "raw_payload_json": json.dumps({"job_id": backend_job_id}, ensure_ascii=False, indent=2),
                }
            )

        values = {
            "job_id": job.id,
            "sku": payload.get("sku"),
            "retailer": payload.get("marketplace"),
            "status": payload.get("status") or "queued",
            "message": payload.get("message"),
            "run_id": run_id,
            "backend_reference": run_id,
            "attempts": int(payload.get("attempts") or 0),
            "max_attempts": int(payload.get("max_attempts") or payload.get("maxAttempts") or 0),
            "error_message": payload.get("error_message") or payload.get("errorMessage"),
            "error_code": payload.get("error_code") or payload.get("errorCode"),
            "marketplace_publication_id": payload.get("marketplace_publication_id"),
            "external_product_id": payload.get("external_product_id"),
            "started_at": self._api_datetime(payload.get("started_at")),
            "finished_at": self._api_datetime(payload.get("finished_at")),
            "raw_payload_json": json.dumps(payload, ensure_ascii=False, indent=2),
        }
        candidate = self.env["publisher.sku"].search([("sku", "=", values["sku"])], limit=1)
        if candidate:
            values["sku_id"] = candidate.id

        line = self.search([("run_id", "=", run_id)], limit=1)
        if line:
            line.write(values)
        else:
            line = self.create(values)
        return line

    @api.model
    def action_sync_runs(self):
        payload = self.env["publisher.job"]._internal_api_request(
            "GET",
            "/internal/publisher/runs",
            params={"status": "queued", "limit": 100},
        )
        runs = payload.get("items") or payload.get("runs") or payload.get("data") or []
        synced_count = 0
        for run_payload in runs:
            if self._upsert_from_run_payload(run_payload):
                synced_count += 1
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Publicador"),
                "message": _("Runs sincronizados: %s") % synced_count,
                "type": "success",
                "sticky": False,
            },
        }

    def action_retry_run(self):
        self.ensure_one()
        if self.status not in ("failed", "skipped"):
            raise UserError(_("Solo se puede reintentar un run fallido u omitido."))
        if not self.run_id:
            raise UserError(_("Este run no tiene runId backend."))
        payload = self.env["publisher.job"]._api_request("POST", "/publisher/runs/%s/retry" % self.run_id)
        self.write(
            {
                "status": payload.get("status") or "queued",
                "message": payload.get("message") or _("Run reencolado."),
            }
        )
        if self.job_id:
            self.job_id.action_refresh_progress()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Publicador"),
                "message": _("Run enviado a reintento."),
                "type": "success",
                "sticky": False,
            },
        }
