/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

class TourDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, loading: true });

        onWillStart(async () => {
            try {
                this.state.data = await this.orm.call(
                    "tour.dashboard",
                    "get_dashboard_data",
                    []
                );
            } catch (e) {
                console.error("Dashboard data load failed:", e);
                this.state.data = { tour_states: [], pending_bookings: [], financial_pending: {} };
            }
            this.state.loading = false;
        });
    }

    navigateToTours(stateFilter) {
        let domain = [];
        if (stateFilter && stateFilter !== "all") {
            domain = [["state", "=", stateFilter]];
        } else if (stateFilter === "all") {
            domain = [["state", "in", ["draft", "pending", "confirmed", "operating", "in_progress", "completed"]]];
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "团队订单",
            res_model: "tour.plan",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
        });
    }

    navigateToBookings(resourceType) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "预订安排",
            res_model: "project.task",
            views: [[false, "list"], [false, "form"]],
            domain: [["resource_type", "=", resourceType], ["state", "=", "01_in_progress"]],
        });
    }

    navigateToPayRequests() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "请款单",
            res_model: "tour.pay.request",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "draft"]],
        });
    }

    navigateToClaims() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "收款认领",
            res_model: "tour.payment.claim",
            views: [[false, "list"], [false, "form"]],
            domain: [["claim_state", "in", ["0", "1"]]],
        });
    }

    navigateToKanban() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "计调看板",
            res_model: "tour.plan",
            views: [[false, "kanban"]],
            domain: [["state", "in", ["confirmed", "operating", "in_progress"]]],
        });
    }

    formatAmount(amount) {
        if (!amount) return "¥0";
        return "¥" + amount.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
}

TourDashboard.template = "tour_base.TourDashboard";
registry.category("actions").add("tour_base.dashboard", TourDashboard);
