/** @odoo-module **/

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class PublisherCandidatesAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            items: [],
            selected: {},
            limit: 24,
            offset: 0,
            total: 0,
            sku: "",
            marketplace: "both",
            listingType: "all",
            detailSku: false,
            loading: false,
            publishing: false,
        });
        onWillStart(() => this.loadPage());

        this._onKeydown = (ev) => {
            if (ev.key === "Escape" && this.state.detailSku) {
                this.closeDetail();
            }
        };
        onMounted(() => window.addEventListener("keydown", this._onKeydown));
        onWillUnmount(() => window.removeEventListener("keydown", this._onKeydown));
    }

    get selectedSkus() {
        return Object.entries(this.state.selected)
            .filter((entry) => entry[1])
            .map((entry) => entry[0]);
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
            const result = await this.orm.call("publisher.sku", "get_candidates_page", [], {
                limit: this.state.limit,
                offset,
                sku: this.state.sku || false,
                listing_type: this.state.listingType,
            });
            this.state.items = result.items || [];
            this.state.offset = result.pagination.offset || 0;
            this.state.limit = result.pagination.limit || this.state.limit;
            this.state.total = result.pagination.total || 0;
            this.state.selected = {};
            this.state.detailSku = false;
        } finally {
            this.state.loading = false;
        }
    }

    async searchSku(ev) {
        ev.preventDefault();
        await this.loadPage(0);
    }

    clearSearch() {
        this.state.sku = "";
        this.loadPage(0);
    }

    changeListingType() {
        this.loadPage(0);
    }

    get hasActiveFilters() {
        return Boolean(this.state.sku) || this.state.listingType !== "all";
    }

    resetFilters() {
        this.state.sku = "";
        this.state.listingType = "all";
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

    toggleSku(sku) {
        this.state.selected[sku] = !this.state.selected[sku];
    }

    openDetail(sku) {
        this.state.detailSku = sku;
    }

    closeDetail() {
        this.state.detailSku = false;
    }

    get detailItem() {
        if (!this.state.detailSku) {
            return null;
        }
        return this.state.items.find((item) => item.sku === this.state.detailSku) || null;
    }

    formatBool(value) {
        return value ? "Si" : "No";
    }

    openPermalink(item) {
        if (item.permalink) {
            window.open(item.permalink, "_blank", "noopener");
        }
    }

    selectPage() {
        const shouldSelect = this.selectedSkus.length !== this.state.items.length;
        for (const item of this.state.items) {
            this.state.selected[item.sku] = shouldSelect;
        }
    }

    marketplacesForPublish() {
        if (this.state.marketplace === "both") {
            return ["oncity", "fravega"];
        }
        return [this.state.marketplace];
    }

    async publishSelected() {
        const skus = this.selectedSkus;
        if (!skus.length) {
            this.notification.add("Selecciona al menos una card.", { type: "warning" });
            return;
        }
        this.state.publishing = true;
        try {
            const action = await this.orm.call("publisher.sku", "publish_skus", [], {
                skus,
                marketplaces: this.marketplacesForPublish(),
            });
            await this.action.doAction(action);
        } finally {
            this.state.publishing = false;
        }
    }
}

PublisherCandidatesAction.template = "sku_publisher_panel.CandidatesAction";

registry.category("actions").add("sku_publisher_panel.candidates_action", PublisherCandidatesAction);
