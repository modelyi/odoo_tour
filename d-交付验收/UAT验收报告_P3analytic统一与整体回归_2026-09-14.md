# UAT 验收报告：P3 analytic 统一 + 本轮整体回归

- 测试时间：2026-09-14
- 环境：http://127.0.0.1:8070（admin/admin，uid=2 Administrator），数据库 tms，容器 tms-odoo / tms-db / tms-redis
- 验证方式：odoo shell（事务内，不落库）+ JSON-RPC API + 源码核对 + 无头浏览器（页面加载/登录）
- 结论：**通过验收（PASS）**，无 P0/P1 阻断；4 个已知 P2 问题仍在（P2-1 范围扩大为 11 条）。

---

## 一、环境健康

| 检查项 | 结果 |
|---|---|
| /web/login 返回 200 | ✅ PASS |
| 容器 healthy | ✅ PASS（tms-odoo / tms-db / tms-redis 均 healthy） |
| JSON-RPC 登录 admin | ✅ PASS（uid=2，is_admin=True） |

## 二、P3 analytic 统一（重点）

| 检查项 | 预期 | 实测 | 结果 |
|---|---|---|---|
| `_ensure_project()` 建 project 且 project.account_id == plan.analytic_account_id | 同一 id | `ensure_project_analytic_same_as_plan=True`（project.account_id 与 plan.analytic_account_id 同 id） | ✅ PASS |
| `_ensure_project()` 幂等 | 二次调用不重复建 | `ensure_project_idempotent=True`（proj.id==proj2.id） | ✅ PASS |
| 已有 project 的团 analytic 无分裂 | 无 | `project_analytic_mismatches=[]` | ✅ PASS |
| 1:1 约束（不重复建） | 唯一 | project.project 有 `unique(tour_plan_id)`；account.analytic.account 有 `unique(tour_plan_id)`；analytic_total=82478 = analytic_with_tour_plan=82478（全部 1:1） | ✅ PASS |
| 成本侧/收入侧同源 | 同一 analytic | 代码：project.task→project.account_id；vendor bill→accounting_mixin 用 plan.analytic_account_id；income_move_id→plan.analytic_account_id。project.account_id==plan.analytic_account_id 保证同源 | ✅ PASS |
| 一团一核算不分裂 | 1:1 | tour.plan.account 以 plan_id 1:1 建台账（_ensure_plan_account 幂等） | ✅ PASS |

**架构链（已核对源码）**：tour.plan.analytic_account_id（1:1，确认时 `_ensure_analytic_account` 幂等创建）→ tour.plan.project_id（1:1，`_ensure_project` 幂等创建，project.account_id 绑定同一 analytic）→ project.task 回链 project → 成本/收入凭证均指向 plan.analytic_account_id。

## 三、本轮改动整体回归

| 模块 | 检查项 | 实测 | 结果 |
|---|---|---|---|
| 团管理 | project/crm 已装 | project、crm 均 installed | ✅ |
| 团管理 | tour.booking 已删 | `env['tour.booking']` KeyError；ir.model 中 tour.booking 残留 0 | ✅ |
| 团管理 | project.task 替代 booking | project.task.resource_type（guide/vehicle/hotel/meal/scenic）EXISTS，plan_code 回链 | ✅ |
| 团管理 | 计调角色授权 | 计调(101)、计调强制安排(35=group_tour_operation_force_assign)、销售(103) 均存在 | ✅ |
| 导游三层 | tour.guide 有 employee_id + partner_id | 2139 活跃导游全部有 employee_id 和 partner_id；34 归档导游亦全部有 employee_id（无缺失） | ✅ |
| 导游三层 | 2173 导游已迁移 | 导游总数（含归档）2173；hr.employee 总数 2501 = 2173 导游 + 328 非导游员工 | ✅ |
| 导游三层 | 抽样验证 | hr.employee 2173「申俊义」→ tour.guide 8368 + partner 14769，三层贯通 | ✅ |
| 费用借款 | 菜单在 Expenses | 导游借款(644)、导游报账(645) parent=Expenses | ✅ |
| 费用借款 | 1221.01 员工借款 | account 63「其他应收款—员工借款」code=1221.01 | ✅ |
| 财务融合 | accounting 唯一入口 + 旅行社财务分组 | 顶级菜单 Accounting(151) 唯一财务入口；旅行社财务(646) 挂其下，仅绑定组 102「财务」 | ✅ |
| 财务融合 | 权限分层 | 组 102「财务」implied=[Accountant(26), 旅行社用户(98)]；计调/销售不含财务组 | ✅ |
| 界面改造 | 订单 kanban + smart button | tour.plan kanban 视图 3402 存在；状态 6 态（草稿318/运营224） | ✅ |
| 界面改造 | 导游列表 | tour.guide.list(1026) 存在，2139 行 | ✅ |
| 存货卸载 | stock 及集成模块 uninstalled | stock/sale_stock/purchase_stock/website_sale_stock/stock_account/stock_landed_costs/stock_dropshipping/mrp/point_of_sale/mrp_account/purchase_requisition/stock_picking_batch/repair 全部 uninstalled；含 stock 字样的 installed 模块 = 0 | ✅ |
| 存货卸载 | 业务模块 installed | sale/purchase/account/project/crm/delivery installed；tour_* 11 模块全 installed | ✅ |
| 存货卸载 | 应用抽屉无存货 | 顶级菜单无 Inventory/存货（has_inventory_menu=False） | ✅ |

## 四、回归已知 P2 问题（验证仍在，记录不修复）

| 编号 | 描述 | 本轮实测 | 状态 |
|---|---|---|---|
| P2-1 | 单星号脱敏残留「陈*」「无*」 | **仍在，且范围扩大**：res.partner 4 条（12784「陈*」/13355「1*」/14662「无*」/14786「毕*」）、tour.guide 3 条（8261「无*」/6954「1*」/8385「毕*」）、hr.employee 4 条（208「陈*」/759「1*」/2066「无*」/2190「毕*」），共 11 条单星号残留。双星号 `**` 残留 = 0 | ⚠️ 仍在（较上次 2 条扩至 11 条） |
| P2-2 | 车辆列表「车牌号」列重复 | **仍在**：根因确认——tour.vehicle 两个字段 `name`（line16）与 `licence`（line42）`string` 均为「车牌号」，且 list 视图（tour_vehicle_views.xml line41-42）同时展示两字段 | ⚠️ 仍在 |
| P2-3 | 4 会计菜单无中文翻译 | **仍在**：Recurring Invoices(504)、Management(485)、Actions(505)、Currency Revaluation(484) 均无 zh_CN | ⚠️ 仍在 |
| P2-4 | 「会计」下两个同名「资产」菜单 | **仍在**：486「Assets」与 501「Assets」均挂 Accounting/Accounting，同名重复 | ⚠️ 仍在 |

## 五、数据观察（非缺陷，建议 dev 确认）

| 编号 | 描述 |
|---|---|
| O-1 | 0 个团已有 project（plan_with_project=0），224 个运营中团尚无 project，13 个运营中团无 analytic。均为懒创建设计（进入计调/确认时幂等补建），非数据错误，但如需存量团立即可点「计调任务」需先触发一次 `_ensure_project`。 |
| O-2 | project.task 仅 1 条，且为 Odoo 默认欢迎任务（id=1「欢迎Administrator！」project_id=null、resource_type=false），非 tour.booking 迁移产物；tour.booking 数据未见迁移到 project.task（可能原 booking 数据量本身为 0 或迁移未执行，建议 dev 说明）。 |
| O-3 | crm.lead 总数 0，crm.lead 转团功能已装但无测试数据。 |
| O-4 | tour.guide.loan / tour.guide.real.pay 数据 0，借款/报账功能已装（菜单+账户就绪）但无测试数据。 |
| O-5 | delivery 仍 installed（运输/承运人模块，非存货本体，销售/发票承运字段依赖，属预期保留）。 |

## 六、整体结论

- [x] ✅ 通过验收

P3 analytic 统一核心目标达成：团=project=analytic 三者 1:1 共享同一 analytic account，`_ensure_project` 幂等、不重复建，成本侧与收入侧同源，单团核算不分裂。

本轮 5 组改动（团管理/导游三层/费用借款/财务融合/界面/存货卸载）全部回归无破坏。

遗留 4 个已知 P2 轻微问题（P2-1 单星号脱敏残留由 2 条扩至 11 条需 dev 关注），均不影响业务可用性，建议转 dev-odoo 下一轮修复。
