/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.actionService = useService("action");
    },

    async onMlCatalogSync() {
        await this.actionService.doAction("ml_catalog_panel.action_sync_ml_products");
        await this.model.root.load();
        this.render();
    },
});
