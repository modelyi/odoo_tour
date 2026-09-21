/** @odoo-module **/

import { Component, onRendered, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { Layout } from "@web/search/layout";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";

export class FinancialReportView extends Component {
    static template = "tour_accounting.FinancialReportView";
    static props = { ...standardActionServiceProps };
    static components = { Layout };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            reportData: null,
            loading: true,
            periods: [],
            periodId: false,
            expandedRows: new Set(),
            visibleRows: [],
            showDebitCredit: true,
            reportName: "",
            currencyId: false,
        });

        const params = this.props.action.params || {};
        this.wizardModel = params.wizard_model || "financial.report";
        this.wizardId = params.wizard_id || false;
        // period_id passed from the wizard
        const wizardPeriodId = params.period_id || false;

        onWillStart(async () => {
            // Load available accounting periods
            try {
                const periods = await this.orm.searchRead(
                    "tour.account.period",
                    [],
                    ["id", "name", "date_start", "date_end"],
                    { order: "date_start desc", limit: 24 }
                );
                this.state.periods = periods;

                // Default to wizard's period, or the first (most recent) period
                if (wizardPeriodId) {
                    this.state.periodId = wizardPeriodId;
                } else if (periods.length > 0) {
                    this.state.periodId = periods[0].id;
                }
            } catch (e) {
                // Periods load failed, continue without
            }

            if (this.wizardId) {
                // Load wizard defaults (debit_credit flag)
                try {
                    const wizardData = await this.orm.read(
                        this.wizardModel, [this.wizardId],
                        ["debit_credit"]
                    );
                    if (wizardData && wizardData.length) {
                        this.state.showDebitCredit = wizardData[0].debit_credit !== false;
                    }
                } catch (e) {
                    // Use defaults
                }
            }
            await this.loadReport();
        });

        onRendered(() => {
            if (this.state.reportName) {
                this.env.config.setDisplayName(this.state.reportName);
            }
        });
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                this.wizardModel,
                "get_online_report_data",
                [this.wizardId, this.state.periodId || false]
            );

            if (data.error) {
                this.notification.add(data.error, { type: "danger" });
                return;
            }

            this.state.reportData = data;
            this.state.showDebitCredit = data.show_debit_credit;
            this.state.currencyId = data.currency;
            this.state.reportName = data.report_name || "";

            // Expand all rows by default
            this.state.expandedRows = new Set(data.expanded_rows || []);
            this._updateVisibleRows();
        } catch (error) {
            this.notification.add(
                _t("加载报表失败: ") + (error.message || ""),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    _updateVisibleRows() {
        if (!this.state.reportData || !this.state.reportData.tree) {
            this.state.visibleRows = [];
            return;
        }
        const rows = [];
        this._flattenTree(this.state.reportData.tree, rows);
        this.state.visibleRows = rows;
    }

    _flattenTree(nodes, result, depth) {
        depth = depth || 0;
        for (const node of nodes) {
            result.push(Object.assign({}, node, { depth: depth }));
            if (node.has_children && this.state.expandedRows.has(node.id)) {
                this._flattenTree(node.children, result, depth + 1);
            }
        }
    }

    formatMoney(value) {
        if (!value && value !== 0) return "";
        return formatMonetary(value, {
            currencyId: this.state.currencyId,
        });
    }

    toggleRow(rowId) {
        if (this.state.expandedRows.has(rowId)) {
            this.state.expandedRows.delete(rowId);
        } else {
            this.state.expandedRows.add(rowId);
        }
        this._updateVisibleRows();
    }

    expandAll() {
        if (this.state.reportData) {
            this.state.expandedRows = new Set(this.state.reportData.expanded_rows || []);
            this._updateVisibleRows();
        }
    }

    collapseAll() {
        this.state.expandedRows = new Set();
        this._updateVisibleRows();
    }

    async drillDown(row) {
        try {
            const action = await this.orm.call(
                "financial.report",
                "get_drilldown_action",
                [],
                {
                    account_id: row.account_id || false,
                    report_id: row.report_id || false,
                    period_id: this.state.periodId || false,
                }
            );
            this.actionService.doAction(action);
        } catch (error) {
            this.notification.add(
                _t("钻取失败: ") + (error.message || ""),
                { type: "danger" }
            );
        }
    }

    onPeriodChange(ev) {
        this.state.periodId = parseInt(ev.target.value, 10) || false;
        this.loadReport();
    }

    get balanceClass() {
        return "fw-bold";
    }

    getTrClass(row) {
        const classes = [];
        if (row.is_report) {
            classes.push("o_report_section");
        }
        if (row.depth > 0) {
            classes.push("o_report_detail");
        }
        return classes.join(" ");
    }
}

registry.category("actions").add("tour_accounting.financial_report", FinancialReportView);
