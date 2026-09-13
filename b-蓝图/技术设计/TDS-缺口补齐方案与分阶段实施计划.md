# TDS-缺口补齐方案与分阶段实施计划

> 文档编号：TDS-GAP-001
> 版本：v1.0
> 日期：2026-09-13
> 编写角色：product-architect（Odoo 架构师）
> 依据：易途系统功能调研.md（247 菜单）、Odoo功能映射方案.md、TDS-模块划分.md、BS-02/03/05/06/07/08、现有 9+ 个 tour_* 模块源码
> 目标：补齐 TMS 相对易途的功能/数据缺口，**先跑通核心主线 → 再补齐 → 不无限扩展**，**能原生就不自建**

---

## 0. 现状盘点与缺口判定

### 0.1 实际已实现（与「14 模块蓝图」有偏离，以源码为准）

现有模块（12 个 addons，其中 11 个 tour_*）：

| 模块 | 已实现核心模型 | 状态 |
|------|--------------|------|
| tour_base | 基础抽象/公司扩展 | ✅ |
| tour_product | tour.line / tour.line.type / tour.line.detail / tour.departure / tour.biz.type / tour.pay.way / tour.base.item | ✅（数据未补全） |
| tour_order | tour.plan / tour.plan.reg / tour.merge / tour.plan.change | ✅（数据已迁移 86,925 计划 / 86,753 报名） |
| tour_operation | tour.booking（guide/vehicle/hotel/meal/scenic 通用预订 + 冲突检测） | ✅（数据 0 条） |
| tour_resource | tour.guide / tour.vehicle / res.partner 扩展(sup_type) / tour.shop.agreement | ✅（数据已迁移） |
| tour_shopping | tour.shop.record（简版） | ⚠️ 简版 |
| tour_accounting | tour.payment.claim(+line) / tour.reconciliation(+line,13类型) / tour.commission / tour.dunning / tour.invoice / tour.bank.account / tour.pay.channel / tour.plan.account + **fork base_accounting_kit**（损益表/资产负债表/总账/试算/往来账龄/现金流/税表/资产/预算/银行对账/PDC/催收/循环） | ✅（财务底座齐） |
| tour_report | tour.report.wizard + 原生 pivot/graph（4 报表） | ⚠️ 仅 4 报表 |
| tour_website | B2C 官网（tour.plan.reg 报名） | ✅ |
| tour_budget | fork account_budget | ✅ |
| tour_tutor | 菜单/向导 | ✅ |

> 关键结论：**财务底座（account + l10n_cn + analytic 一团一核算 + 复式分录）已就绪且健壮**，`tour.accounting.mixin` 已封装 `_tour_get_account(code)` / `_tour_make_move()` / `_tour_get_journal()` 与完整科目表（1001/1002/1122.01/2203/2241/2221/6401.xx/6001.xx 等）。后续财务功能**一律薄层 + 走 account.move**，不自建分录引擎。

### 0.2 缺口分类

| 类别 | 缺口 | 本质 |
|------|------|------|
| A 数据缺口 | 发团计划(1条)/行程明细(2条)/购物记录(0)/计调预订(0)/业务类型字典 | **迁移/派生脚本缺失**，模型已存在 |
| B 功能缺口 | 购物管理完整化 / 导游借款报账 / P2P付款 / 二次结算 / 审核流程 / 报表与分析 | **薄业务层缺失**，底座已就绪 |

---

## 1. 数据补缺方案（A 类）

> 统一原则：数据源全部来自 `a-调研/et_data/`（28 对 CSV+JSON），模型均已存在，只需**补迁移脚本**（仿 `scripts/migrate_et_data.py` 的流式+幂等写法）。**不动模型结构**（除行程明细需补 1 个字段外）。

### 1.1 发团计划 tour.departure（1 → 数千条）

| 项 | 方案 |
|----|------|
| **数据源** | `team_orders.csv`（已迁入 tour.plan）的 `LineID + BeginDate` 组合；价格取 `line_products.csv` 的 AdultPrice/ChildPrice |
| **目标模型** | tour.departure（已存在，字段：line_id/start_date/end_date/seats/booked_seats/price_adult/price_child/state） |
| **派生方式** | 以 `(line_id, begin_date)` 为自然键分组 tour.plan：`seats = Σ plan_num`（团队人数上限）、`booked_seats = Σ guest_count`、`price_adult/child = tour.line.adult_price/child_price`、`start_date=begin_date`、`end_date=end_date`、`state = published`（源已出团则 ended） |
| **边界** | 仅对 `biz_mode in (12 DSK 团期计划)` 或**所有 line+date 组合**生成？——决策：**对所有非 cancelled plan 的 (line,begin_date) 去重生成**，DSK(12) 优先标记为"可报名"；其余作为"实际发团记录"兜底。不追求与易途"团期计划"菜单一一对应 |
| **验收** | `tour.departure` 条数 ≈ tour.plan 去重(line_id,begin_date) 数；余位 = seats - booked_seats ≥ 0 |

### 1.2 行程明细 tour.line.detail（2 → 数千条）

| 项 | 方案 |
|----|------|
| **数据源** | tour.line.details_rich（Html，源自 LineDetailsRich 富文本） |
| **目标模型** | tour.line.detail（已存在，字段：line_id/day_no/title/city/meal_*/hotel/traffic/content/sequence） |
| **迁移方式** | 写**富文本解析器**（BeautifulSoup 已在依赖中）：按 `<h1/h2/h3/strong>` 或"第N天/DAY N"标题切分 → 提取 day_no、title（标题文本）、city（含"宿/住 XX"或"XX 出发"）、meal_*（含"早/午/晚/餐"关键词）、hotel（"宿 XX"）、traffic（"车/航班/高铁"）、content（该天剩余 HTML 原文）。无法解析的整段降级放入 content 字段 |
| **补字段** | tour.line.detail 增加 `src_html = fields.Html('原文')` 保留原始富文本，便于人工校对与回填（**唯一的模型改动**） |
| **验收** | 抽查 top-20 线路：day_no 连续（1..day_num）、标题/城市/餐/住宿提取正确率 > 80%；未解析内容保留在 src_html 不丢失 |

### 1.3 购物记录 tour.shop.record（0 → 全量）

| 项 | 方案 |
|----|------|
| **数据源** | 易途购物表（调研 2.9 对应 PlanShop 录入/退单/补单、PlanShopCost 成本、ShopAuditChk 查询），以 et_data 中对应 CSV 为准（若未采集到购物明细 CSV，则在 `易途系统数据.db` SQLite 内 `PlanShop*` 表导出） |
| **目标模型** | tour.shop.record（已存在，字段：plan_id/shop_id/agreement_id/guide_id/shop_date/amount/commission_rate/commission_amount/remark + 唯一约束 plan+shop+date） |
| **迁移方式** | 按自然键 `(plan_code → tour.plan, 购物店 → res.partner[sup_type=shop], shop_date)` 幂等导入；退单/补单用 `record_type` 字段区分（见 2.1 补字段）；`commission_rate` 优先取 tour.shop.agreement.rebate_rate 匹配，无协议取源值 |
| **依赖** | 依赖 1.1/1.2 先完成（plan/shop/guide 已迁移） |
| **验收** | 购物记录数 > 0 且与易途源表行数一致（去重后）；退单金额为负、补单为正、录入为正 |

### 1.4 计调预订 tour.booking（0 → 全量）

| 项 | 方案 |
|----|------|
| **数据源** | 易途预订安排表（2.7 预定安排：PlanGuide_Arrange 派导 / OrderCar_Arrange 用车 / OrderHotelRquire 用房 / OrderMeal 用餐 / OrderScenic 门票），et_data 对应 CSV |
| **目标模型** | tour.booking（已存在，resource_type 分 guide/vehicle/hotel/meal/scenic + 类型专属字段 + 冲突检测） |
| **迁移方式** | 五类安排单分别映射：`resource_type` → 目标资源字段（guide_id / vehicle_id / supplier_id[sup_type=hotel/meal/scenic]）；日期区间、人数、金额按类型公式带入；**迁移时 `with_context(bypass_conflict_check=True)`** 跳过冲突检测（历史数据允许重叠） |
| **依赖** | 依赖 tour.plan + tour.guide + tour.vehicle + res.partner 已迁移 |
| **验收** | 五类 booking 数 > 0；派导/派车 booking 关联到有效 guide/vehicle；供应商类型约束全部通过 |

### 1.5 业务类型字典 tour.biz.type（空 → 5+ 条）

| 项 | 方案 |
|----|------|
| **数据源** | 易途基础数据 `ItemType` 表（业务类型）→ et_data 对应 CSV |
| **目标模型** | tour.biz.type（已存在，name/code/help_code/brief/sequence/active） |
| **迁移方式** | 直接导入基础数据分类为"业务类型"的子集；同时将 tour.plan 的 `plan_class` / `reg_order_type` 等源字符串字典值登记为 tour.biz.type 供下拉复用 |
| **验收** | 业务类型字典非空；与易途 ItemType 业务类型子集条数一致 |

> **A 类总原则**：只补脚本、不重构模型；全部走 `scripts/migrate_et_data.py` 同款流式+幂等+断点续跑，关闭 mail 追踪（`MIGRATE_CTX`）。

---

## 2. 功能补齐方案（B 类）

> 统一决策准则：**能用 Odoo 原生（account/purchase/pivot/graph/状态机）就不自建；自建仅做"薄业务层"，分录/报表/审批全挂原生**。明确**不自建通用审批引擎 tour_approval**（原蓝图 17 人天，砍掉）。

### 2.1 购物管理完整化（易途 20 菜单 → 自建薄层 + 原生统计）

| 决策项 | 结论 |
|--------|------|
| 原生 vs 自建 | **自建薄层**（tour.shop.record 扩展），**统计全用原生 pivot/graph**，**批量收款用原生 account.payment** |
| 归属模块 | tour_shopping |
| 关键模型/字段 | 扩展 tour.shop.record：`record_type`(Selection: normal 录入 / return 退单 / supplement 补单)、`cost_amount`(购物成本，源自 PlanShopCost)、`refund_amount`、`net_amount`(净额=amount+cost 语义)、`settle_state`(未结算/已收款/已对账)、`payment_id`(Many2one account.payment 批量收款回写) |
| 批量收款 | 向导：选中 shop.record → 生成 account.payment(收款，对方=购物店，analytic=团分析账户)，回写 payment_id + settle_state |
| 统计（导游业绩/购物店/项目/组团社/客源地/年龄/性别/线路购物） | **不建报表模型**。在 tour.shop.record 加可分组字段：`guest_province/guest_nation/guest_age_group/guest_sex`（compute 自 tour.plan.reg 报名客源地/年龄/性别；**需在 tour.plan.reg 补 age/sex 字段**），然后为每个统计口径建 pivot/graph 视图（复用 tour_report 的 REPORT_TYPES 模式） |
| 退单/补单 | 用 `record_type` 区分，金额正负记账；不新建退单/补单模型 |

### 2.2 导游借款 / 报账（费用报销 + 借款冲抵）

| 决策项 | 结论 |
|--------|------|
| 原生 vs 自建 | **自建薄层**（3 模型）+ **分录走 account.move**（复用 tour.accounting.mixin）。**不强制 hr.expense**——导游非员工、借款冲抵/一团一核算/差额征税可扣除标记/个税是旅行业特有，hr.expense 强套反而扭曲 |
| 归属模块 | tour_accounting（不新建 tour_guide_expense） |
| 关键模型/字段 | 按 BS-06 §10 落地：`tour.guide.loan`（guide_id/plan_id/amount/purpose/account_id/state[待审批/已审批/已放款/已冲抵]/approver_id/disburser_id/due_date=放款+30天）；`tour.guide.real.pay`（guide_id/plan_id/expense_line_ids/total_amount/loan_id/balance）；`tour.guide.expense.line`（expense_type[车/餐/门票/房/导服/其他]/amount/supplier_id/invoice_no/attachment/deductible/account_id） |
| 分录 | 放款：借 1221.01 其他应收款-导游借款 / 贷 1002 银行存款；报账：借 6401.xx 成本 / 贷 1221.01（完全冲抵）；差额补款/退款按 BS-06 §8.3。**需在 mixin 补 2 个科目码**：`ACCOUNT_GUIDE_LOAN='1221.01'`、`ACCOUNT_PAYABLE_SUP='2202'` |
| 个税 | 复用 tour.commission 已实现的个税代扣逻辑（2221.05），导游分成走 commission 不走报账 |
| 校验 | 借款≠审批≠放款三方分离（BS-06 R-27）、30 天报账预警、未冲抵禁新借（R-30），用 @api.constrains + cron |

### 2.3 付款 P2P（采购到付款）

| 决策项 | 结论 |
|--------|------|
| 原生 vs 自建 | **原生 purchase + account.move(vendor bill) + account.payment 做底座**，自建**请款单**做审批前置 |
| 归属模块 | tour_accounting（请款单）+ tour_operation（booking 确认时生成应付源头） |
| 关键模型/字段 | `tour.pay.request`（=BS-06 plan.pay.audit.flow：plan_id/supplier_id/cost_type[10类]/amount/pay_way_id/account_id/invoice_ids/reason/applicant_id/apply_date/state/audit_level/audit_history_ids/payment_id） |
| 链路 | **tour.booking(confirmed) → 生成 vendor bill(account.move, analytic=团分析账户, cost_type→科目映射) → 请款单审批(分级阈值) → account.payment 付款(原生 register payment) → 核销应付** |
| 成本类型→科目映射 | 新增一个配置表/字典：车费→6401.01、房费→6401.02、餐费→6401.03、门票→6401.04、地接→6401.05、导服→6401.07、保险→6401.06（差额征税可扣除项打 `deductible` 标记，衔接 tour.invoice 差额征税） |
| 分级审批 | 免审≤1000 / 一级 1001-5万 / 二级 5万-20万 / 三级>20万 双签（BS-06 §4.2），阈值存 res.config.settings，**用请款单 state 机实现，不建通用引擎** |

### 2.4 二次结算

| 决策项 | 结论 |
|--------|------|
| 原生 vs 自建 | **自建薄层** `tour.order.return`（=BS-07 plan.order.return），分录走 account.move |
| 归属模块 | tour_accounting |
| 关键模型/字段 | plan_id/supplier_id/return_type(追加/退款)/amount/reason/attachment_ids/state[待审核/已审核/已驳回]/applicant_id/apply_date/auditor_id/audit_date/audit_opinion + move_id |
| 分录 | 追加：借 6401.xx 成本 / 贷 2202 应付；退款反向（BS-07 §4.12.4/5） |
| 分级审批 | ≤500 财务主管 / 500-5000 财务经理 / >5000 总经理（BS-07 §3.4），**申请人≠审核人强制校验** |

### 2.5 审核流程（计调审核/财务审核/归档 + 订单审核 + 收付审核）

| 决策项 | 结论 |
|--------|------|
| 原生 vs 自建 | **不自建 tour_approval 通用引擎**。复用 tour.plan **现有状态机**（draft→pending→confirmed→operating→in_progress→completed→archived，已含 action_confirm/operate/start/complete/archive）+ 已存在的 audit_chk/audit_chk0/verify_chk 标志位 |
| 计调审核[3361] | = tour.plan 状态 `confirmed→operating`（action_operate），操作人=计调角色 |
| 财务审核[125] | = tour.plan 增加 `finance_audit_state`(未审/已审/退回) + `finance_auditor_id/date`，通过后才可 archive；**归档[154]** = action_archive 前置校验：该团所有 booking 已完成对账、无未冲抵借款（复用 tour.reconciliation/tour.guide.loan 状态） |
| 订单审核[6581] | = tour.plan `pending→confirmed`（action_confirm 二段）+ audit_chk0 初审/audit_chk 审核回写 |
| 收付审核[3612/3613/3075] | = 请款单分级 state 机（见 2.3）+ 收款认领已有三步闭环（tour.payment.claim state 机已实现） |
| 归属模块 | tour_order（订单/计调/归档审核）+ tour_accounting（收付审核） |

### 2.6 报表扩展 + 数据分析（易途 40+ vs 当前 4）

| 决策项 | 结论 |
|--------|------|
| 原生 vs 自建 | **不引入第三方报表引擎**。继续用 tour_report 的 `REPORT_TYPES` 向导 + **原生 pivot/graph/list 视图**模式，**绝大多数报表零新模型，只加 REPORT_TYPES 条目 + search 视图 + 分组字段** |
| 归属模块 | tour_report |
| 已有底座 | 财务报表（损益/资产负债/总账/试算/账龄/现金流/税表）已由 tour_accounting fork 覆盖，**不需重复造** |
| 第一批补齐（P0，覆盖核心主线） | ①应收团款统计[1589]/查询[1588]（基于 tour.plan sum_un_pay + 账龄）②收款明细[1619]/汇总[1621]（tour.payment.claim）③付款明细[1622]/汇总[1623]（account.payment+请款单）④用车[1599/1598]/订房[3363/3362]/订餐[3367/3366]/门票[3365/3364]统计（tour.booking 按 resource_type 分组）⑤导游带团[3382]/借款[3371]/交款[3381]/报账[3369/3370]（tour.guide.loan/real.pay）⑥二次结算查询[3988] |
| 第二批补齐（P1，数据分析 16 项） | 分项成本分析/单团诊断（tour.plan.account + tour.booking 按 cost_type）、客户收客/线路收客/产品销售/客人地域（tour.plan 按 supplier/line/province）、计调/外联年度与业绩（tour.plan 按 sales_name/user）、部门业绩/经营统计月报（tour.plan.account 按 department/月）。**全部 pivot/graph，按需增加可分组字段** |
| 边界 | 不建独立 BI 模块、不建数据仓库，Odoo 原生 pivot/graph + 收藏视图即为"分析看板" |

---

## 3. 分阶段实施计划

> 排序原则：**先让 7 环节核心主线能端到端跑通（数据到位 + 最小闭环）→ 再补齐财务深化 → 最后按价值补报表**；每阶段给出依赖与验收标准。

### Phase 0 — 数据补缺（先让主线有数据可跑）

**范围**：§1 全部（1.1~1.5 迁移脚本）
**依赖**：tour.plan/reg/guide/vehicle/partner 已迁移（✅ 已完成）
**交付物**：`scripts/migrate_et_data.py` 增加第三批（departure/line.detail/shop.record/booking/biz.type）
**验收标准**：
- [ ] 发团计划/行程明细/购物记录/计调预订/业务类型字典 5 项数据量 > 0 且与源数据可对账
- [ ] 计调预订 5 类 resource_type 均有关联到有效资源，无供应商类型约束冲突
- [ ] 迁移脚本幂等（重跑不重复）
- [ ] B2C 官网能展示发团计划（tour.departure）与结构化行程（tour.line.detail）

### Phase 1 — 核心主线最小闭环（购物 + 导游借款报账 + P2P + 二次结算 + 审核）

**范围**：§2.1（购物完整化）、§2.2（导游借款报账）、§2.3（P2P）、§2.4（二次结算）、§2.5（审核流程）
**依赖**：Phase 0（有 booking/shop.record 数据）；tour.accounting.mixin 科目补齐（1221.01/2202）
**交付物**：
- tour_shopping：record_type/cost/net/payment_id + 批量收款向导 + 退单/补单
- tour_accounting：tour.guide.loan / tour.guide.real.pay / tour.guide.expense.line / tour.pay.request / tour.order.return
- tour_order：finance_audit_state + 归档前置校验
- mixin 科目 + 成本类型→科目映射字典
**验收标准（逐条对应 §2）**：
- [ ] 购物：录入→退单→补单→成本→批量收款→按店/导游/客源地/年龄/性别统计全链路可走通，收款回写 account.payment
- [ ] 导游借款：申请→审批→放款→报账→冲抵（含补款/退款/完全冲抵三分支）分录正确，30 天预警 + 未冲抵禁新借生效
- [ ] P2P：booking 确认 → vendor bill → 请款分级审批 → account.payment → 应付核销，一团一核算 analytic 正确
- [ ] 二次结算：追加/退款审核后生成正确分录，申请人≠审核人拦截
- [ ] 审核：订单审核→计调审核→出团→完成→财务审核→归档 状态机严格单向；未对账/未冲抵借款的团不可归档

### Phase 2 — 报表与分析补齐

**范围**：§2.6 第一批（P0 核心报表 12~15 张）+ 第二批（数据分析 16 项按价值排序）
**依赖**：Phase 1（有 shop.record/loan/booking/pay.request/order.return 数据可统计）
**交付物**：REPORT_TYPES 条目扩展 + pivot/graph 视图 + 可分组字段补齐（tour.plan.reg.age/sex 等）
**验收标准**：
- [ ] 应收/收/付/用车/房/餐/门票/导游借款报账/二次结算 核心报表可出数且与 account.move 汇总一致
- [ ] 单团利润报表（已有）与新增分项成本分析口径一致（都基于 tour.plan.account）
- [ ] 数据分析 16 项中 P1 高价值项（分项成本/收客/业绩/地域）可用 pivot/graph 自助分析

### Phase 3 — 明确不做（范围冻结）

**不做**（已在范围排除，此处冻结边界）：
- 票务 tour_ticket、同业分销 tour_b2b、小程序 API tour_api、支付宝费控、车队管理系统、SaaS tour_saas、AI tour_ai
- 不连外部系统（无支付网关/无银行直连/无短信/无税控直连）
- 支付全线下（收款认领/付款 account.payment 均为线下登记）
- 不做通用审批引擎 tour_approval（用状态机替代）
- 不做独立 BI/数据仓库（用原生 pivot/graph）

---

## 4. 关键架构决策汇总（决策日志）

| # | 决策 | 理由 | 替代方案（被否） |
|---|------|------|-----------------|
| D1 | 财务分录全走 account.move，自建只做薄层 | 复用 Odoo 复式记账/对账/报表底座，避免自建记账引擎 | 自建分录表（被否：重复造轮子） |
| D2 | 不自建通用审批引擎 | 审批场景少且各有状态机，通用引擎 17 人天 ROI 低 | tour_approval 通用引擎（砍掉） |
| D3 | 导游报账不用 hr.expense | 借款冲抵/一团一核算/差额征税/个税是旅行业特有，员工报销模型不匹配 | hr.expense 强套 |
| D4 | P2P 用 purchase + vendor bill + account.payment | 采购到应付到付款 Odoo 原生闭环成熟 | 自建付款单（被否） |
| D5 | 报表用 pivot/graph 扩展，不建报表引擎 | 原生透视/图形即分析看板，零第三方依赖 | 引入 BI/报表引擎 |
| D6 | 发团计划按 (line,begin_date) 派生 | tour.plan 是事实源，departure 是投影视图 | 手工维护发团计划 |
| D7 | 购物/计调数据用迁移脚本补，不改模型 | 模型已就绪，缺的是数据 | 重新设计模型 |

---

## 5. 依赖关系与风险

### 5.1 依赖链

```
Phase 0（数据迁移）
   ├─ 依赖：tour.plan/reg/guide/vehicle/partner 已迁移 ✅
   └─ 产出：departure/line.detail/shop.record/booking/biz.type 数据
        ↓
Phase 1（功能闭环）
   ├─ 依赖：Phase 0 数据 + mixin 科目补齐
   └─ 产出：购物/借款报账/P2P/二次结算/审核
        ↓
Phase 2（报表）
   └─ 依赖：Phase 1 业务数据
```

### 5.2 主要风险与缓解

| 风险 | 等级 | 缓解 |
|------|:----:|------|
| 行程富文本解析率不达标（LineDetailsRich 结构不统一） | 🟡 中 | 保留 src_html 原文 + 人工校对 top-N；解析失败降级 content |
| 易途购物/预订明细 CSV 未采集 | 🔴 高 | 从 `易途系统数据.db`(SQLite 374MB) 导出 PlanShop*/PlanOrderAssign 等表；若确无则明示为"不可迁移"并列入遗留 |
| P2P 链路长（booking→bill→请款→付款）落地成本高 | 🟡 中 | 先跑通 vendor bill→请款→付款最小闭环，booking 自动生成 bill 作为增强后置 |
| 分期推进中 scope 蔓延 | 🟡 中 | Phase 3 范围冻结 + 决策日志 D1~D7 挂靠 |
| 审核状态机与既有 state 字段语义冲突 | 🟡 中 | 财务审核用独立 finance_audit_state 字段，不改现有 state 枚举 |

---

## 6. 待确认事项（需要业务/BA 拍板）

1. 发团计划的生成口径：仅 DSK(12) 团期计划，还是所有非 cancelled 团都生成（本方案默认后者，需 tour-ba 确认）
2. 购物统计的"客源地/年龄/性别"粒度：基于报名单(tour.plan.reg)客人维度，需确认年龄区间划分规则
3. 成本类型→科目映射表（10 类）的最终科目编码，需 finance-ba 按 BS-05 科目表确认
4. 请款/二次结算/借款的分级审批阈值，是否按 BS-06/07 默认值上线（默认值已写入本方案）
