/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, "sku_publisher_panel.ListController", {
    setup() {
        this._super(...arguments);
        this.actionService = useService("action");
    },

    async onPublisherRefreshCandidates() {
        await this.actionService.doAction("sku_publisher_panel.action_refresh_publisher_skus");
        await this.model.root.load();
        this.render();
    },
});
