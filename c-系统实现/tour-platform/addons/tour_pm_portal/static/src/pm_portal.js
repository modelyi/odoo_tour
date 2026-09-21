/** @odoo-module **/

import { jsonrpc } from "@web/core/network/rpc_service";
import { _t } from "@web/core/l10n/translation";

document.addEventListener("DOMContentLoaded", function () {
    const actionButtons = document.querySelectorAll(".pm-action-btn");

    actionButtons.forEach((btn) => {
        btn.addEventListener("click", async function (e) {
            e.preventDefault();
            const depId = this.dataset.depId;
            const action = this.dataset.action;

            if (action === "cancel") {
                if (!confirm(_t("确定要取消这个班期吗？此操作不可撤销。"))) {
                    return;
                }
                try {
                    const result = await jsonrpc(
                        `/my/pm/departure/${depId}/action`,
                        {
                            action: "cancel",
                        }
                    );
                    if (result.success) {
                        alert(_t("班期已取消"));
                        location.reload();
                    } else {
                        alert(result.error || _t("操作失败"));
                    }
                } catch (err) {
                    alert(_t("请求失败：") + err.message);
                }
            } else if (action === "adjust_seats") {
                const newSeats = prompt(
                    _t("请输入新的总位数（当前：") +
                        this.closest(".list-group-item").querySelector(".text-muted")
                            .textContent +
                        _t("）")
                );
                if (!newSeats || !/^\d+$/.test(newSeats)) {
                    return;
                }
                try {
                    const result = await jsonrpc(
                        `/my/pm/departure/${depId}/action`,
                        {
                            action: "adjust_seats",
                            new_seats: newSeats,
                        }
                    );
                    if (result.success) {
                        alert(result.message);
                        location.reload();
                    } else {
                        alert(result.error || _t("操作失败"));
                    }
                } catch (err) {
                    alert(_t("请求失败：") + err.message);
                }
            }
        });
    });
});
