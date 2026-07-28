from odoo import api, fields, models


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

    def action_open_candidates(self):
        return self.env.ref("sku_publisher_panel.action_publisher_candidates_cards").read()[0]

    def action_refresh_candidates(self):
        result = self.env["publisher.sku"].action_refresh_candidates()
        return self._with_reload(result)

    def action_open_jobs(self):
        return self.env.ref("sku_publisher_panel.action_publisher_job").read()[0]

    def action_sync_recent_jobs(self):
        result = self.env["publisher.job"].action_sync_recent_jobs()
        return self._with_reload(result)

    def action_open_runs(self):
        return self.env.ref("sku_publisher_panel.action_publisher_run").read()[0]

    def action_sync_runs(self):
        result = self.env["publisher.job.line"].action_sync_runs()
        return self._with_reload(result)

    def _with_reload(self, result):
        """Chain a same-page reload after the notification so the KPI counts
        on the dashboard refresh immediately instead of waiting for a manual F5."""
        if isinstance(result, dict) and result.get("tag") == "display_notification":
            reload_action = self.env.ref("sku_publisher_panel.action_publisher_dashboard").read()[0]
            reload_action["context"] = {"stackPosition": "replaceCurrentAction"}
            result.setdefault("params", {})["next"] = reload_action
        return result
