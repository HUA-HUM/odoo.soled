/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, "sku_publisher_panel.ListController", {
    setup() {
        this._super(...arguments);
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
    },

    async onPublisherRefreshCandidates() {
        await this.actionService.doAction("sku_publisher_panel.action_refresh_publisher_skus");
        await this.model.root.load();
        this.render();
    },

    async onPublisherSyncJobs() {
        await this.actionService.doAction("sku_publisher_panel.action_sync_publisher_jobs");
        await this.model.root.load();
        this.render();
    },

    async onPublisherCreateJob(methodName) {
        const selectedIds = this.model.root.selection.map((record) => record.resId);
        if (!selectedIds.length) {
            this.notification.add("Selecciona al menos un SKU.", { type: "warning" });
            return;
        }
        const action = await this.orm.call("publisher.sku", methodName, [selectedIds]);
        if (action) {
            await this.actionService.doAction(action);
        }
    },
});
