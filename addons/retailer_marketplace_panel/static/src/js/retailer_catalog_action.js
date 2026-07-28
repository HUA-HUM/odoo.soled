/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class RetailerCatalogAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.model = this.props.action.params.model;
        this.marketplaceName = this.props.action.params.title || "";
        this.state = useState({
            items: [],
            limit: 100,
            offset: 0,
            total: 0,
            search: "",
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

    async loadPage(offset = this.state.offset) {
        this.state.loading = true;
        try {
            const result = await this.orm.call(this.model, "get_catalog_page", [], {
                limit: this.state.limit,
                offset,
                search: this.state.search || false,
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.limit = result.pagination.limit || this.state.limit;
            this.state.total = result.pagination.total || 0;
        } finally {
            this.state.loading = false;
        }
    }

    async searchProducts(ev) {
        ev.preventDefault();
        await this.loadPage(0);
    }

    clearSearch() {
        this.state.search = "";
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

    async syncAllProducts() {
        this.state.syncingAll = true;
        try {
            const result = await this.orm.call(this.model, "action_sync_products", []);
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
            res_model: this.model,
            res_id: item.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openLink(item, ev) {
        ev.stopPropagation();
        if (item.link) {
            window.open(item.link, "_blank");
        }
    }
}

RetailerCatalogAction.template = "retailer_marketplace_panel.CatalogAction";

registry.category("actions").add("retailer_marketplace_panel.catalog_action", RetailerCatalogAction);
