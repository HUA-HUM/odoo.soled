/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MODEL = "retailer.marketplace.change";

class RetailerChangesAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            items: [],
            limit: 24,
            offset: 0,
            total: 0,
            sku: "",
            marketplace: "",
            status: "",
            loading: false,
            syncingAll: false,
        });
        onWillStart(() => this.loadPage());
    }

    get currentPage() {
        return Math.floor(this.state.offset / this.state.limit) + 1;
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.state.total / this.state.limit));
    }

    get hasPrevious() {
        return this.state.offset > 0;
    }

    get hasNext() {
        return this.state.offset + this.state.limit < this.state.total;
    }

    statusClass(status) {
        const value = (status || "").toLowerCase();
        if (value.includes("fail") || value.includes("error")) {
            return "is-failed";
        }
        if (value.includes("complet") || value.includes("success") || value.includes("done")) {
            return "is-completed";
        }
        return "is-pending";
    }

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        try {
            const result = await this.orm.call(MODEL, "get_changes_page", [], {
                limit: this.state.limit,
                offset,
                sku: this.state.sku || false,
                marketplace: this.state.marketplace || false,
                status: this.state.status || false,
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.limit = result.pagination.limit || this.state.limit;
            this.state.total = result.pagination.total || 0;
        } finally {
            this.state.loading = false;
        }
    }

    async searchChanges(ev) {
        ev.preventDefault();
        await this.loadPage(0);
    }

    clearSearch() {
        this.state.sku = "";
        this.state.marketplace = "";
        this.state.status = "";
        this.loadPage(0);
    }

    previousPage() {
        if (this.hasPrevious) {
            this.loadPage(Math.max(0, this.state.offset - this.state.limit));
        }
    }

    nextPage() {
        if (this.hasNext) {
            this.loadPage(this.state.offset + this.state.limit);
        }
    }

    async syncAllChanges() {
        this.state.syncingAll = true;
        try {
            const result = await this.orm.call(MODEL, "action_sync_all", []);
            if (result && result.params && result.params.message) {
                this.notification.add(result.params.message, { type: result.params.type || "success" });
            }
            await this.loadPage(0);
        } finally {
            this.state.syncingAll = false;
        }
    }

    openDetail(item) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: item.id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

RetailerChangesAction.template = "retailer_marketplace_panel.ChangesAction";

registry.category("actions").add("retailer_marketplace_panel.changes_action", RetailerChangesAction);
