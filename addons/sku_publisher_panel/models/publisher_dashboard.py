from odoo import api, fields, models


class PublisherDashboard(models.Model):
    _name = "publisher.dashboard"
    _description = "SKU Publisher Dashboard"

    name = fields.Char(default="Dashboard")
    total_candidates = fields.Integer(compute="_compute_counts")
    ready_count = fields.Integer(compute="_compute_counts")
    pending_oncity_count = fields.Integer(compute="_compute_counts")
    pending_fravega_count = fields.Integer(compute="_compute_counts")
    no_stock_count = fields.Integer(compute="_compute_counts")
    error_jobs_count = fields.Integer(compute="_compute_counts")

    @api.depends()
    def _compute_counts(self):
        sku_model = self.env["publisher.sku"]
        job_model = self.env["publisher.job"]
        for dashboard in self:
            dashboard.total_candidates = sku_model.search_count([])
            dashboard.ready_count = sku_model.search_count([("ready_to_publish", "=", True)])
            dashboard.pending_oncity_count = sku_model.search_count([("published_oncity", "=", False)])
            dashboard.pending_fravega_count = sku_model.search_count([("published_fravega", "=", False)])
            dashboard.no_stock_count = sku_model.search_count([("publish_status", "=", "no_stock")])
            dashboard.error_jobs_count = job_model.search_count([("status", "=", "error")])

    def action_open_candidates(self):
        return self.env.ref("sku_publisher_panel.action_publisher_sku").read()[0]

    def action_refresh_candidates(self):
        return self.env["publisher.sku"].action_refresh_candidates()
