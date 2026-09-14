# TDS-团管理标准模块承载方案

> 文档编号：TDS-ARCH-002
> 版本：v1.0
> 日期：2026-09-14
> 状态：初稿
> 编写角色：product-architect（产品架构师）
> 依据：TDS-ARCH-001 系统架构设计、TDS-MOD-001 模块划分、TDS-GAP-001 缺口补齐方案、TDS-FIN-001 财务记账对接、BS-02 订单管理、BS-03 计调操作、BS-10/11 财务、tour_order/tour_operation/tour_accounting 源码
> 回答的核心问题：**团（tour.plan）能不能用 project/task 管理？能不能用 CRM 承载？尽量用 Odoo 19 原生，能原生不自建，自建只做旅行社特有薄层，不破坏现有已跑通主线（O2C/P2P 凭证 30 万条、团 8.6 万条）**

---

## 0. 结论先行（TL;DR）

**一句话结论**：团主档（tour.plan）必须保留自建（它是「运营+财务」复合载体，project/CRM 都缺金额/发票/收款/税/报名/并团能力，不可替代），但**计调调度层迁到 project.task（看板+甘特图），销售跟单层迁到 crm.lead（漏斗→赢单自动建团），财务继续走 account.move + analytic**——即「销售前段用 CRM、团主档自建 tour.plan、计调用 project.task、财务用 account」的四层分工，团 = project = analytic account 三者 1:1 共享核算。

| 生命周期层 | 承载模块 | 模式 | 现状 → 目标 |
|-----------|---------|------|------------|
| 销售跟单（成团前） | **crm.lead** | 原生 + 薄扩展 | 无 → 新增 |
| 团主档（成团后运营+财务） | **tour.plan（自建保留）** | 自建薄层 | 保留，不加层 |
| 计调调度（派导/车/房/餐/票） | **project.project + project.task** | 原生 + 薄扩展 | tour.booking（空表）→ 迁移 |
| 财务（凭证/发票/收款/税） | **account.move + analytic** | 原生 | 已就绪，不动 |

---

## 1. 背景与目标

### 1.1 用户提出的两个问题

1. 「团是不是可以用 project/task 来管理？」
2. 「或者是不是能用 CRM 的标准功能承载团的管理？」

### 1.2 现状（以源码为准）

| 项 | 现状 |
|----|------|
| 团主档 `tour.plan` | 自建，137 字段（标识/业务分类 12 种/日期/人数/房型/接送/金额 5 类/归属/状态机/并团溯源/备注），已挂 `mail.thread`，**已融合 analytic 一团一核算** |
| 计调 `tour.booking` | 自建（tour_operation），**数据 0 条**（源未采集），`resource_type` selection 分 guide/vehicle/hotel/meal/scenic，含冲突检测/座位预警/金额公式/二次确认，未实现 |
| 报名 `tour.plan.reg` | 自建，人数/房型/证件/并团字段 |
| 财务 | 已融合进 accounting（唯一入口），差额征税/收款认领/单团核算全走 `account.move` + analytic，收入确认凭证 `income_move_id`、成本账单 `cost_bill_id` 已回链 |
| 已装标准模块 | `account`/`sale`/`analytic`/`contacts`/`hr`/`website`/`portal`（经 manifests 确认）；**`crm`/`project`/`purchase`/`hr_expense` 均未安装** |

### 1.3 约束（不可破坏）

- 财务融合已就绪：accounting 是唯一分录入口，`tour.accounting.mixin` 已封装 `_tour_get_account/_tour_make_move/_tour_get_journal` + 完整科目表
- 数据已迁移：团 8.6 万、报名 8.6 万、凭证 30 万
- 界面改造、O2C（收入确认）、P2P（成本应付账单）已跑通

---

## 2. 团生命周期完整梳理

> 一条团从「获客」到「结算归档」的 7 个阶段，每阶段标注核心活动、关键数据、标准模块匹配结论。

| # | 阶段 | 核心活动 | 关键数据 | 标准模块匹配 | 承载决策 |
|---|------|---------|---------|-------------|---------|
| 1 | **销售跟单** | 客户建档、线路询价、报价、跟进、赢单/输单 | 客户(partner)、销售员、意向线路、预期金额、预期出发日、跟进行程 | **crm.lead**（漏斗/activity/预测/团队）✅ 高度匹配 | **用 CRM** |
| 2 | **成团** | 赢单转正式团、签合同、定业务模式、确认人数房型、预收款 | 团号、业务模式、合同号、人数房型、金额(报价/收款)、来源渠道 | project ❌ 缺金额/报名；CRM ❌ 漏斗终点即成交 | **tour.plan 自建**（CRM won 触发建团） |
| 3 | **计调调度** | 派导、派车、订房、订餐、订门票，冲突检测、二次确认 | 资源对象、日期区间、人数/房数/桌数、成本金额、确认状态 | **project.task**（看板+甘特图+任务状态）✅ 高度匹配 | **用 project.task** |
| 4 | **出团** | 出团前置校验（资源到位）、投保、接站、送酒店 | 出团状态、集合确认、资源确认清单 | project ✅ 校验视图 | tour.plan 状态机 + project 校验 |
| 5 | **行程中** | 导游报账、购物记录、借款冲抵、二次结算 | 费用明细、购物金额、借款/冲抵 | account（费用报销）部分匹配；旅行社特有（借款冲抵/个税）自建 | **account.move + 自建薄层** |
| 6 | **收尾** | 完成团、确认收入（预收→收入拆税）、差额征税抵减、发票、收款认领 | 收入确认凭证、抵减凭证、发票、应收余额 | account（复式分录/发票/收款）✅ 原生 | **account 原生** |
| 7 | **核算** | 单团核算台账、账龄分析、利润、归档 | analytic.line 汇总、可扣除成本、抵减额、利润 | account + analytic（一团一核算）✅ 原生 | **account.analytic 原生** |

**关键洞察**：阶段 2/4/5/6 的「金额/发票/收款/税/报名/并团」是 project 和 CRM 都**结构性缺失**的能力；阶段 1 是 CRM 的天然主场；阶段 3 是 project 的天然主场。因此「团」不是一个东西，而是**一条跨越销售/运营/财务的多段生命周期**，单靠任一标准模块都无法端到端承载，必须分层。

---

## 3. 各标准模块适用性评估

### 3.1 project（project.project / project.task）

| 维度 | 结论 | 理由 |
|------|------|------|
| 承载「团主档」 | ❌ **不能用** | project 是任务/交付物管理：有看板/甘特/里程碑/工时/任务依赖/分配人，但**无金额、无发票、无收款、无税务、无报名人数、无房型、无并团溯源**。tour.plan 137 字段中约 50% 是财务/报名/金额类，project 无法承接 |
| 承载「计调调度」 | ✅ **能用（推荐）** | 派导/派车/订房/订餐/门票本质是「团期内一批带日期/资源/责任人的执行任务」，project.task 的看板（Kanban）+ 甘特（Gantt）+ 阶段（stage）+ 分配人（assignee）完美覆盖；且**免费获得资源时间轴冲突可视化** |
| 承载「出团前置校验」 | ✅ 部分用 | 校验逻辑（资源确认/二次确认）仍自建薄层，但可在 project.task 的 stage 上表达「待确认/已确认/已完成」，甘特图直观暴露未就位资源 |
| 承载「单团核算」 | ✅ **天然绑定** | project.project 原生 1:1 `account.analytic.account`（`analytic_account_id`），团=project 即可共享 analytic，见 §4.4 |

**结论**：project 不替代团主档，**专门接管计调层**。

### 3.2 CRM（crm.lead）

| 维度 | 结论 | 理由 |
|------|------|------|
| 承载「团主档」 | ❌ **不能用** | crm.lead 是销售漏斗：lead→opportunity→won/lost，**成交即终点**，无运营（计调/出团/核算）、无财务（金额仅为 `expected_revenue` 预期值，无真实发票/收款/税）。团主档是「成交后的运营+财务载体」，语义在 CRM 之外 |
| 承载「成团前销售跟单」 | ✅ **能用（推荐）** | 客户建档、线路意向、报价、跟进、赢单/输单，正是 crm.lead 的 pipeline + activity + 预测 + 销售团队 的核心能力，**免费获得销售漏斗/跟进/预测** |
| won → 自动建团 | ✅ 薄扩展 | `crm.lead` 标记 won 后，通过 server action/按钮触发创建 `tour.plan`（draft），回写 `lead_id` 溯源（见 §4.3） |

**结论**：CRM 不承载团主档，**专门接管销售前段**。

### 3.3 sale（sale.order）

| 维度 | 结论 | 理由 |
|------|------|------|
| 承载「团主档」 | ❌ **不用** | sale.order 是「报价单→销售订单→标准开票」闭环，但 tour.plan 有 12 种业务模式（含代订 41 净额法、并团、内部流转 16、共享协议 71），收入确认走「预收→收入拆税」而非标准开票，差额征税/收款认领/并团/人数房型均非 sale 语义 |
| 作为底层依赖 | ✅ **保留** | `tour_accounting` 已 depends on `sale`，借用其 account/analytic 底座；不引入 sale.order 单据流 |
| B2C 线上销售 | ✅ 已决策不走 sale | TDS-B2C-001 已定：报名走 tour.plan.reg + tour.payment.claim 线下付款，复用收款认领 |

**结论**：sale 保持「底层依赖」定位，不承载团主档、不建 sale.order 单据流。

### 3.4 account（account.move / account.analytic）

| 维度 | 结论 | 理由 |
|------|------|------|
| 承载「财务全部」 | ✅ **原生（已就绪）** | 复式分录、发票、收款、差额征税抵减、一团一核算 analytic、账龄，全部走 account.move + analytic，`tour.accounting.mixin` 已封装，30 万凭证已生成 |
| 承载「单团核算」 | ✅ **原生** | tour.plan 已 1:1 analytic account，核算台账从 analytic.line 派生（记账真相） |

**结论**：account 是财务唯一入口，**保持现状不动**，仅需与 project 的 analytic 统一（§4.4）。

---

## 4. 最终架构建议

### 4.1 分层模块映射（目标态）

```
┌────────────────────────────────────────────────────────────────────┐
│                         销售前段（成团前）                            │
│  crm.lead ──(_inherit 薄扩展)──► x_line_id/x_biz_mode/x_begin_date  │
│     │ won 触发建团                                                    │
└─────┼───────────────────────────────────────────────────────────────┘
      ▼
┌────────────────────────────────────────────────────────────────────┐
│                     团主档（成团后运营+财务）                          │
│  tour.plan（自建保留，137 字段不动）                                  │
│   ├─ 业务模式/人数/房型/接送/并团溯源/金额 ← 旅行社特有，自建          │
│   ├─ analytic_account_id（一团一核算，1:1）                           │
│   ├─ project_id（1:1 团=project，新增回链）                           │
│   └─ lead_id（销售溯源，新增回链）                                     │
└─────┬──────────────────────────┬────────────────────────────────────┘
      │ 计调                     │ 财务
      ▼                         ▼
┌──────────────────────┐  ┌────────────────────────────────────────┐
│  计调调度（project）   │  │  财务（account）                          │
│  project.project     │  │  account.move + analytic                 │
│   │ 1:1 tour.plan    │  │   ├─ 收入确认 income_move_id（已就绪）      │
│   │ 1:1 analytic     │  │   ├─ 成本应付 cost_bill_id（已就绪）        │
│   ▼                  │  │   ├─ 差额征税抵减（已就绪）                 │
│  project.task        │  │   ├─ 收款认领/发票（已就绪）                │
│   │ = 计调预订        │  │   └─ 单团核算 tour.plan.account（已就绪）  │
│   │ resource_type    │  │                                          │
│   │ 看板+甘特图       │  │  ← 三者共享同一个 analytic account         │
└──────────────────────┘  └────────────────────────────────────────┘
```

### 4.2 团主档 tour.plan：保留哪些、转哪些

**结论：tour.plan 全量保留，不删字段、不转标准模块**。理由：

- 137 字段中财务/金额/报名/并团/人数房型类是 project/CRM 结构性缺失，无处可转
- 8.6 万团 + 30 万凭证 + 报表（按 sales_name/supplier/line 分组）+ 界面改造已依赖这些字段
- 唯一新增 2 个「回链」字段（薄扩展，不迁移历史、可空）：

| 新字段 | 类型 | 用途 | 历史数据 |
|--------|------|------|---------|
| `project_id` | Many2one project.project | 团=project 回链，计调看板入口 | 可空（老团不强制补） |
| `lead_id` | Many2one crm.lead | 销售溯源（哪个机会赢单成团） | 可空 |

**「接单」字段迁移决策**（订单来源 from_type / 销售员 sales_name / 客户 supplier_id / 业务模式 biz_mode）：

| 字段 | CRM 承载？ | tour.plan 保留？ | 结论 |
|------|-----------|-----------------|------|
| 客户 supplier_id | crm.lead.partner_id | ✅ 保留（冗余） | won 时写入，CRM 为源头，tour.plan 冗余兼容报表 |
| 销售员 sales_name | crm.lead.user_id | ✅ 保留（冗余） | 同上 |
| 订单来源 from_type | crm.lead.medium/source（或 x_from_type） | ✅ 保留 | 同上 |
| 业务模式 biz_mode | crm.lead.x_biz_mode（_inherit 加字段） | ✅ 保留（required） | biz_mode 是团的核心分类，CRM 阶段需预选以决定建团类型，won 时带入 |

> 原则：**CRM 是「新业务」的销售源头，tour.plan 字段保留为「兼容历史 + 报表分组」的冗余快照**，不反向迁移 8.6 万历史团。

### 4.3 计调调度：project.task 设计

#### 4.3.1 project 结构

| 对象 | 设计 |
|------|------|
| project.project | **一团一 project**，`name = 团号-团名`，`analytic_account_id = tour.plan.analytic_account_id`（共享），`_inherit` 加 `tour_plan_id`（1:1 唯一约束） |
| project.task | **一预订一 task**（派导/派车/订房/订餐/门票 = 5 类 task），`project_id` 挂到团 project |

#### 4.3.2 资源类型映射：selection 字段，不是 task type/stage

**核心结论**：派导/派车/订房/订餐/门票是「任务类型」（分类维度），**不是** project.task 的 `stage_id`（流水线状态维度）。二者必须分离：

| 维度 | 承载 | 取值 |
|------|------|------|
| **类型（是什么）** | 自建 `resource_type`（Selection，_inherit project.task） | guide/vehicle/hotel/meal/scenic |
| **状态（到哪一步）** | 原生 `stage_id`（project.task.type，可复用或按团定制） | 待安排 → 已确认 → 已完成（+ 二次确认态） |

> Odoo project 原生**没有**「任务类型」维度（stage 是状态机、tags 是标签），因此资源类型必须是 project.task 的自建 selection 字段；状态则复用原生 stage，让 Kanban 按「待确认/已确认/已完成」分列，Gantt 按日期排程。

#### 4.3.3 project.task 字段设计（_inherit 薄扩展）

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `resource_type` | Selection | 自建 | guide/vehicle/hotel/meal/scenic，必填 |
| `guide_id` | Many2one tour.guide | 自建 | 派导（domain audit_chk=True） |
| `vehicle_id` | Many2one tour.vehicle | 自建 | 派车（domain audit_chk=True） |
| `supplier_id` | Many2one res.partner | 自建 | 房/餐/票（domain 按 sup_type） |
| `date_start`/`date_end` | Datetime | 原生 project.task | 资源占用日期区间（Gantt 用） |
| `planned_hours`/`user_ids` | 原生 | 原生 | 计调员/导游分配 |
| `partner_id` | 原生 | 原生 | 供应商 |
| `amount_total` | Float | 自建 | 预订成本（金额公式，同 tour.booking） |
| `guest_count` | Integer | 自建 | 人数/间数/桌数 |
| 类型专属字段 | — | 自建 | 房型 5 项/餐次桌数餐标/票价 4 类票数/导服费/车费（**从 tour.booking 原样平移**） |
| `force_reason/force_user/force_date` | 自建 | 自建 | 强制安排留痕 |

#### 4.3.4 与 tour.plan 的关联 + 旅行社特有逻辑（自建薄层）

| 逻辑 | 实现 | 说明 |
|------|------|------|
| 冲突检测（导游/车辆日期区间重叠） | `_inherit project.task` @api.constrains + create/write 钩子 | 从 tour.booking `_check_resource_conflict` 平移，同一导游/车辆不同团、日期重叠、非取消即拦截（强制留痕放行） |
| 座位预警 | compute 字段 | `seat_warning`（车辆座 < 人数+司陪） |
| 金额公式 | `_calc_amount_from_vals` 平移 | 导服费/车费/房价×晚×间数/餐标×桌数/票价×票数 |
| 二次确认（房/票） | 自建 `confirm_state` 字段 | 营运中心二次确认，仅 hotel/scenic |
| 出团前置校验 | `tour.plan._check_booking_before_start` 改查 project.task | 从 `tour.booking.search` 改为 `project.task.search(domain=[('project_id','=',self.project_id.id)])`，校验逻辑不变 |

> **迁移成本低**：tour.booking 现为**空表（0 数据）**，无历史迁移风险；逻辑平移 + 模型从 `tour.booking` 改为 `project.task._inherit`。tour.operation 模块降级为 project.task 的薄扩展模块（或并入 tour_operation 重构）。

### 4.4 销售前段：CRM 设计

#### 4.4.1 crm.lead 薄扩展字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `x_line_id` | Many2one tour.line | 意向线路（报价/建团依据） |
| `x_biz_mode` | Selection（复用 tour_base BIZ_MODE） | 业务模式预选（决定建团类型） |
| `x_begin_date` | Date | 预期出发日期 |
| `x_from_type` | Selection | 订单来源（替代 lead.medium 或冗余） |
| `x_plan_id` | Many2one tour.plan | 赢单后回写建团结果（溯源） |

#### 4.4.2 won → 自动建团流程

```
crm.lead (opportunity, 有 x_line_id + x_biz_mode + partner_id)
   │  action_set_won（赢单）
   ▼
server action / 按钮「转团」→ 创建 tour.plan（state=draft）
   ├─ line_id      ← lead.x_line_id
   ├─ biz_mode     ← lead.x_biz_mode
   ├─ supplier_id  ← lead.partner_id
   ├─ sales_name   ← lead.user_id.name（冗余）
   ├─ from_type    ← lead.x_from_type
   ├─ begin_date   ← lead.x_begin_date
   └─ lead_id      ← lead.id（回链溯源）
   ▼
后续按现有主线走：action_confirm（自动建 analytic + 台账）→ 计调（project.task）→ 出团 → 完成（收入确认）
```

> 关键：**tour.plan 的 analytic/台账自动创建时机不变**（仍是 confirmed 触发），CRM 建团只落 draft，不提前触发财务，避免与 O2C 主线冲突。

#### 4.4.3 历史数据策略

- 8.6 万历史团**无 CRM lead**，`lead_id` 可空，不 backfill
- CRM 是**可选的新业务入口**，现有「直接录团」路径保留（from_type=内部 1 的手工录入场景仍直接建 tour.plan）

### 4.5 analytic 单团核算与 project 的 analytic 统一

**目标**：团 = project = analytic account，三者 1:1 共享同一个 `account.analytic.account`，避免「成本挂 project 的 analytic、收入挂 tour.plan 的 analytic」导致单团核算分裂。

**现状**：tour.plan 已实现 `_ensure_analytic_account()`（confirmed 时幂等创建，`analytic_account_id` 1:1）。

**统一方案**（`_ensure_project()` 幂等，在 `_ensure_analytic_account` 后调用）：

```python
def _ensure_project(self):
    """确保团队有 1:1 project（幂等），共享既有 analytic account。"""
    self.ensure_one()
    if self.project_id:
        return self.project_id
    if not self.analytic_account_id:
        self._ensure_analytic_account()
    # 关键：project 直接绑定 tour.plan 已有的 analytic account，
    # 不重复创建（account.analytic.account 有 project_id 反向字段）
    project = self.env['project.project'].create({
        'name': '%s-%s' % (self.plan_code, self.plan_name),
        'analytic_account_id': self.analytic_account_id.id,  # 共享
        'tour_plan_id': self.id,
    })
    self.project_id = project.id
    return project
```

**保证**：
- 成本侧（booking→vendor bill，analytic=project 的 analytic）与收入侧（income_move，analytic=tour.plan 的 analytic）指向**同一个 account.analytic.account**
- project.project 原生 `analytic_account_id` 是 account.analytic.account 的 One2one 反向（`account.analytic.account.project_id`），绑定后 project 与 analytic 天然一致
- tour.plan.account 的核算继续从 analytic.line 派生，口径不变

---

## 5. 自建 vs 原生边界

### 5.1 必须自建（旅行社特有，无法原生）

| 能力 | 载体 | 理由 |
|------|------|------|
| 团主档 | tour.plan | 12 业务模式/人数房型/接送/并团溯源/金额 5 类 |
| 报名 | tour.plan.reg | 人数房型/证件（加密）/并团挂接 |
| 差额征税 | tour.invoice + vat_deduct 凭证 | 销项税额抵减、可扣除成本分摊（CAS 22/36/37 特有） |
| 并团 | tour.merge / first_plan_id | 散客并团溯源 |
| 收款认领 | tour.payment.claim | 线下收款与团/客户的认领闭环 |
| 单团核算台账 | tour.plan.account | 差额扣除口径/账龄/发票缺口（业务口径快照） |
| 计调冲突检测/金额公式/二次确认 | project.task._inherit | 资源日期重叠/座位预警/房票二次确认（行业特有） |
| 导游借款/报账 | tour.guide.loan/real.pay | 借款冲抵/个税/差额可扣除（TDS-GAP D3 已决策不用 hr.expense） |

### 5.2 原生承载（不自建）

| 能力 | 载体 |
|------|------|
| 计调任务看板/甘特/状态 | project.project / project.task / project.task.type |
| 销售漏斗/跟进/预测 | crm.lead + activity |
| 财务分录/发票/收款/税 | account.move / account.payment / account.analytic |
| 报表/分析 | 原生 pivot/graph（TDS-GAP D5） |
| 采购到付款 | purchase + vendor bill + account.payment（TDS-GAP D4） |

### 5.3 自建薄层扩展原生（_inherit，不动核心模型）

| 扩展点 | 内容 |
|--------|------|
| project.task._inherit | resource_type + 5 类专属字段 + 冲突检测 + 金额公式 + 二次确认 |
| project.project._inherit | tour_plan_id（1:1）+ 共享 analytic 绑定 |
| crm.lead._inherit | x_line_id/x_biz_mode/x_begin_date/x_from_type/x_plan_id + won→建团 |
| tour.plan._inherit | project_id / lead_id 回链 |

---

## 6. 分阶段改造路径

> 原则：**新增强、不迁移、不破坏**——project/crm 均为新增可空字段 + 新流程，8.6 万团/30 万凭证/已跑通 O2C/P2P 主线零回填、零改写。

| 阶段 | 目标 | 改动 | 风险 | 验收 |
|------|------|------|------|------|
| **P0 评估装模块** | 确认 project/crm 与现有模块兼容 | 安装 `project`、`crm`（纯新增，不改现有模型）；验证不冲突 | 🟢 低（crm/project 独立，不影响 account/sale） | 现有 tour.plan/account 全功能回归通过；模块可卸载 |
| **P1 计调 project.task 化** | tour.booking（空表）→ project.task | 新建 project.task._inherit（resource_type + 5 类字段 + 冲突检测 + 金额公式 + 二次确认）；`tour.plan._ensure_project()`；`_check_booking_before_start` 改查 project.task；tour.booking 保留只读或冻结 | 🟡 中（逻辑平移需回归；出团前置校验依赖点变更） | 5 类预订可建/冲突拦截/甘特图排程/出团校验通过；tour.booking 0 数据无迁移 |
| **P2 销售 CRM 化** | crm.lead 承载销售跟单 | crm.lead._inherit 加 5 字段；won→建团 server action；tour.plan 加 lead_id | 🟡 中（建团映射需与 biz_mode/line 对齐） | lead 赢单→自动建 draft 团→确认→analytic 正常；直接录团路径不受影响 |
| **P3 analytic 统一验证** | 团=project=analytic 共享 | `_ensure_project` 幂等绑定既有 analytic；验证成本/收入侧同 analytic | 🟡 中（双写 analytic 是最大风险点） | 单团核算 income_total/cost_total 不裂；project 成本与 tour.plan 收入汇入同一 analytic |
| **P4 冻结/观察** | 稳定期 | 记录决策日志；明确不做（ticket/b2b/saas/ai） | 🟢 低 | 主线 O2C/P2P/差额征税持续健康 |

**依赖链**：P0 → P1（project.task 依赖 project）→ P2（CRM 独立，可与 P1 并行）→ P3（依赖 P1 的 project+analytic 绑定）→ P4。

---

## 7. 结论（回答用户两个问题）

1. **「团能不能用 project/task 管理？」** —— **团主档不能**（project 缺金额/发票/收款/税/报名/并团），但**计调调度层应该用 project.task**（看板+甘特图+资源冲突可视化是免费且匹配的能力）。正解是「团主档自建 tour.plan + 计调 project.task 分层」。

2. **「能不能用 CRM 承载团管理？」** —— **团主档不能**（CRM 漏斗终点即成交，无运营/财务），但**成团前的销售跟单应该用 CRM**（crm.lead → won 自动建团）。正解是「销售前段 CRM + 团主档 tour.plan 分层」。

**最终推荐架构（四层分工）**：

```
销售跟单 ──► crm.lead（原生+薄扩展）──won──► 建团
团主档   ──► tour.plan（自建保留，137 字段不动 + project_id/lead_id 回链）
计调调度 ──► project.project(1:1团) + project.task（原生看板/甘特 + 薄扩展冲突检测）
财务     ──► account.move + analytic（原生，已就绪，与 project 共享 analytic）
```

**核心不变式**：团 = project = analytic account（1:1:1 共享核算）；accounting 是唯一分录入口；自建只做旅行社特有薄层（差额征税/并团/报名/人数房型/收款认领/冲突检测）。

---

## 8. 决策日志

| # | 决策 | 理由 | 被否替代方案 |
|---|------|------|-------------|
| A1 | 团主档 tour.plan 保留自建，不转 project/CRM/sale | 137 字段中财务/报名/并团/税类 project/CRM 结构性缺失；8.6 万团+报表依赖 | 团=project.project / 团=crm.lead / 团=sale.order（全被否） |
| A2 | 计调调度迁 project.task（替换空表 tour.booking） | 看板+甘特+资源冲突可视化免费获得；tour.booking 0 数据零迁移风险 | 继续自建 tour.booking（被否：重复造看板/甘特） |
| A3 | 资源类型=selection 字段，状态=原生 stage | Odoo project 无「任务类型」维度；stage 是状态机不可混用类型 | 每资源一个 stage / task type（被否：类型态混淆） |
| A4 | 销售跟单迁 crm.lead，won 自动建团 | 漏斗/跟进/预测原生；成交即终点，天然切在「成团」边界 | 团=crm.lead（被否：CRM 无运营/财务） |
| A5 | 团=project=analytic 共享同一 account.analytic.account | 避免成本/收入侧 analytic 分裂，单团核算口径统一 | project 独立建 analytic（被否：核算裂） |
| A6 | project/crm/lead 均为新增可空字段，不 backfill 历史 | 不破坏 8.6 万团/30 万凭证/已跑通 O2C/P2P | 历史团回填 project/lead（被否：成本高、无业务价值） |
| A7 | sale 保持底层依赖，不建 sale.order 单据流 | 12 业务模式/差额征税/并团不匹配标准开票；B2C 已走收款认领 | sale.order 承载团（被否） |

---

## 9. 待确认事项（需 BA/协调人拍板）

1. 计调 project.task 是否彻底废弃 tour.booking，还是「冻结只读 + 后续自然下线」（本方案默认：P1 后 tour.booking 冻结只读，新预订一律走 project.task）
2. CRM 是「全量替换销售跟单」还是「仅新业务启用」（本方案默认：新业务启用，内部直接录团路径保留）
3. project.task 的 stage 是「每团自定义」还是「全局统一 3 段（待安排/已确认/已完成）+ 二次确认态」（本方案默认后者）
4. 计调 module 归属：project.task 薄扩展是否保留在 tour_operation 模块内（本方案默认保留，仅重构内部模型）
