/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.actionService = useService("action");
    },

    async onOncitySync() {
        await this.actionService.doAction("retailer_marketplace_panel.action_sync_oncity_products");
        await this.model.root.load();
        this.render();
    },

    async onFravegaSync() {
        await this.actionService.doAction("retailer_marketplace_panel.action_sync_fravega_products");
        await this.model.root.load();
        this.render();
    },

    async onOncityOrdersSync() {
        await this.actionService.doAction("retailer_marketplace_panel.action_sync_oncity_orders");
        await this.model.root.load();
        this.render();
    },

    async onFravegaOrdersSync() {
        await this.actionService.doAction("retailer_marketplace_panel.action_sync_fravega_orders");
        await this.model.root.load();
        this.render();
    },
});
