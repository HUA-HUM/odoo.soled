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
        return self.env["publisher.sku"].action_refresh_candidates()

    def action_open_jobs(self):
        return self.env.ref("sku_publisher_panel.action_publisher_job").read()[0]

    def action_sync_recent_jobs(self):
        return self.env["publisher.job"].action_sync_recent_jobs()

    def action_open_runs(self):
        return self.env.ref("sku_publisher_panel.action_publisher_run").read()[0]

    def action_sync_runs(self):
        return self.env["publisher.job.line"].action_sync_runs()
