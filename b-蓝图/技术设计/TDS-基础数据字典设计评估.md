# TDS-基础数据与字典设计评估

> 文档编号：TDS-DATA-003
> 版本：v1.0
> 日期：2026-09-14
> 状态：评估稿（待评审，不立即改代码）
> 编写角色：product-architect（产品架构师）
> 依据：tour_base / tour_product / tour_resource / tour_order / tour_operation / tour_accounting 源码、TDS-DATA-001 数据模型设计、Odoo 19 实施规范（万能字典反模式、selection vs M2O、原生复用）
> 回答的核心问题：**TMS 现有的 6 处基础数据/字典设计是否合规，哪些该复用原生、哪些该独立模型、哪些该 selection，迁移成本与优先级如何**

---

## 0. 结论先行（TL;DR）

| # | 字典 | 现状 | 合规判定 | 一句话结论 | 优先级 |
|---|------|------|---------|-----------|--------|
| 1 | `tour.base.item` 万能字典 | 1 表 + `item_type` selection 装 4 类字典 | ❌ **反模式** | 万能字典表，且 4 类字典**全部无业务引用（死数据）**，唯一引用 `level_id` 还缺 domain 限类 | **P0 拆解** |
| 2 | 房型/团餐/交通/团队类型 | 塞进 tour.base.item，实际用 Integer/Selection/Char 硬编码 | ❌ 未复用原生 | 字典与真实建模脱节：房型是固定 5 种（可 selection）、团餐是餐次（已 selection）、交通是 Char | P1 |
| 3 | 职务 | 仅注释声明「改由 hr.job 承载」 | ❌ **只声明未实现** | 无任何 hr.job 数据迁移、无 job_id 字段，需落地 | P1 |
| 4 | `tour.pay.way` 结算方式 | 独立模型 + `pay_type`（4 类），7 条已迁 | ⚠️ 部分合规 | 与 `tour.pay.channel` 两套支付分类重叠；`pay_type` 混淆「支付方式」与「结算条款」 | P1 |
| 5 | `tour.line.type` 线路分类 | 独立树模型（parent_id/parent_path） | ⚠️ 偏离设计 | TDS-DATA-001 原定 `_inherit='product.category'`，实现做成独立模型且 85 条**全部扁平无层级** | **P0 决策** |
| 6 | `res.partner.sup_type` 供应商类型 | 单一 selection（10+签证） | ⚠️ 偏离设计 | TDS-DATA-001 原定 `category_id`（tags），实现做成单选 selection，限制多标签 | P1 |
| 7 | `constants.py` 集中常量 | 5 个 selection 常量集中存放 | ❌ **名存实亡** | 无任何模块 import；且 `BIZ_MODE`(12 项) 与实际 `tour.plan.biz_mode`(15 项) 相互矛盾 | P1 |
| 8 | `company_id` 多公司处理 | 各字典都加 company_id | ❌ 不完整 | 有 company_id 字段但无 ir.rule 隔离、无 `_check_company`；字典加 company_id 本身反原生惯例（字典应全局共享） | P2 |

**总判断**：现有字典设计存在**两个反模式（万能字典、重复真相源）**和**三处偏离既定设计文档（product.category / category_id tags / 原生复用）**。核心问题是「**为了迁数据而造字典表，但字典与真实业务建模脱节，且设计文档与实现分叉**」。改进方向：**能用原生复用的复用原生（product.category、hr.job、account.payment.term、res.partner.category），能 selection 的用 selection（固定枚举），确实需要用户可维护的才建独立 M2O 模型**。

---

## 1. 背景与评估口径

### 1.1 评估维度

对照 Odoo 19 实施规范，对每个字典回答三个问题：

1. **是否万能字典反模式**：一个表 + 一个 `type/kind` selection 装多类互不相关的字典，是 Odoo 社区公认反模式（后果：无 domain 约束、无类型安全、报表/权限无法按类隔离、字段名无语义）。
2. **selection vs M2O**：取值**固定且少、由代码决定** → Selection（内联即可，不必建表）；取值**用户需自行维护、会增长、需带附加属性** → 独立 M2O 模型。
3. **原生复用**：Odoo 已提供的字典/主数据（`product.category`、`product.attribute`、`hr.job`、`account.payment.method`、`account.payment.term`、`res.partner.category`、`uom.uom`）应优先复用，不自建平行模型。

### 1.2 现状事实清单（以源码为准）

| 模型/文件 | 位置 | 关键事实 |
|-----------|------|---------|
| `tour.base.item` | tour_product/models/tour_base_item.py | item_type selection 4 类（room_type/meal_type/transport/team_type），company_id |
| `tour.pay.way` | tour_product/models/tour_pay_way.py | name+code+pay_type（cash/transfer/credit/prepaid），company_id |
| `tour.line.type` | tour_product/models/tour_line_type.py | parent_id+parent_path+child_ids+line_ids，company_id，**独立模型（非 product.category）** |
| `tour.line` | tour_product/models/tour_line.py | **独立模型（非 product.template）**，line_type_id M2O tour.line.type |
| `sup_type` | tour_resource/models/res_partner.py | selection 11 项（10+visa），**单一选择（非 category_id tags）** |
| `level_id` | tour_resource/models/res_partner.py:48 | `Many2one('tour.base.item', '供应商等级')`，**无 domain 限类** |
| `constants.py` | tour_base/models/constants.py | BIZ_MODE/SUP_TYPE/PLAN_TYPE/FROM_TYPE/SEX，**无任何模块 import** |
| 房型字段 | tour_order/tour_plan.py:114、tour_plan_reg.py:96 | 5 个 Integer 硬编码（单/标/三/陪同/加床） |
| 餐次 | tour_operation/project_task.py:84 | meal_type selection（breakfast/lunch/dinner） |
| 交通 | tour_product/tour_line.py:31 | send_traffic/end_traffic Char |
| `tour.pay.channel` | tour_accounting/tour_pay_channel.py | channel_type（bank_transfer/wechat/alipay/cash/other）+ fund_account_id + journal_id |
| 多公司 ir.rule | tour_accounting/security、tour_budget/security | 有 asset/budget 的 multi_company rule；**字典模型无** |

---

## 2. 逐字典评估

### 2.1 `tour.base.item` — 万能字典（反模式）

**现状**：一张表 + `item_type` selection 区分房型/团餐/交通/团队类型 4 类，带 name/help_code/brief/sequence/active/company_id。demo 数据只迁了 9 条（房型 4、团餐 2、交通 3），team_type 0 条；源 items_2/3/5/11/57 共 29 条未迁满（含职务）。

**判定：❌ 反模式**，且比反模式更糟——是「**死字典**」：

1. **万能字典表本身就是反模式**：一个表装 4 类互不相关的字典，无法按类做 domain 约束（见 2.1.1 的 `level_id` 反例）、无法按类设权限/报表、`item_type` 是运行时字符串无类型安全。
2. **4 类字典全部无业务引用**：grep 全库确认，`room_type/meal_type/transport/team_type` 这 4 个取值**没有任何模型字段引用它们**。真实的房型是 5 个 Integer 字段、餐次是 Selection、交通是 Char——字典与真实建模完全脱节。
3. **唯一引用是错的**：`tour_resource/res_partner.py:48` 的 `level_id = Many2one('tour.base.item', '供应商等级')` 直接指向万能字典，**没有 `domain=[('item_type','=','level')]`**——而「供应商等级」这个 item_type 根本不在 4 类里。结果：下拉框能选到房型/团餐/交通，且「供应商等级」无处可维护。

**改进建议（P0 拆解）**：

| 步骤 | 动作 | 迁移成本 | 优先级 |
|------|------|---------|--------|
| 1 | 删除 `tour.base.item` 模型，或将其收敛为**单一语义的独立模型**（见 2.2） | 低（0 业务数据依赖） | P0 |
| 2 | `level_id` 改为独立模型 `tour.supplier.level`（或复用 `res.partner.category` 的「等级」标签） | 低（供应商等级本就无数据） | P0 |
| 3 | 房型/团餐/交通/团队类型按 2.2 各自定性处理，**不共用一张表** | 见 2.2 | P1 |

> 判定依据：Odoo 规范中，字典要么是「固定枚举 → Selection」，要么是「独立业务模型（_name 语义化、可扩展）」。`item_type` 分诊式的通用表是「万能字典」教科书反例。

---

### 2.2 房型 / 团餐 / 交通 / 团队类型 — 各归各位

**现状**：四类本应挂在 `tour.base.item` 里，实际业务建模各走各的：

| 字典 | 实际业务建模 | 当前字典是否被引用 | 定性 |
|------|------------|------------------|------|
| 房型 room_type | `tour.plan`/`tour.plan.reg` 用 5 个 Integer（单/标/三/陪同/加床）；`project.task` 用 room_single/standard/triangle/accompany/additional | ❌ 未引用 | 固定 5 种 → **Selection 或独立枚举** |
| 团餐 meal_type | `project.task.meal_type` Selection（breakfast/lunch/dinner） | ❌ 未引用（字典里的「团餐/自助餐」是餐型，不是餐次，语义都错位） | 餐次=Selection；餐型若需维护→独立模型 |
| 交通 transport | `tour.line.send_traffic/end_traffic` Char（飞机/火车/大巴） | ❌ 未引用 | 固定几种 → **Selection 或 product.attribute** |
| 团队类型 team_type | `tour.guide.group_type` Char（团队类型偏好） | ❌ 未引用（0 数据） | 待定，需 BA 确认业务语义 |

**判定：❌ 未复用原生 + 字典脱节**。核心问题是「**造了字典，但业务字段没用它，而是各自硬编码**」，导致字典成为僵尸数据。

**改进建议**：

1. **房型（room_type）**：这是**固定 5 种**（单间/标间/三人间/陪同房/加床），且业务上表达的是「**数量**」而非「房型字典」——`hotel_room_single=2` 意思是「2 间单间」。房型维度**天然是 Selection 或字段，不该是字典表**。现状的 5 个 Integer 字段其实是**最贴近业务的做法**（每房型一个计数列，报表/公式直接可算），无需改为字典。唯一可优化点是「房型是否可能新增种类」——若会，才考虑 `product.attribute`（Odoo 原生「变体属性」，可自由增属性值，且与 product 集成）；否则保持现状，删除房型字典。
2. **团餐（meal_type）**：语义已分裂——`project.task.meal_type` 是「餐次」（早/中/晚，固定 Selection，正确），字典里的「团餐/自助餐」是「餐型」。**餐次保持 Selection；餐型若需用户维护 → 独立 `tour.meal.type` 模型**（或复用 product.category），但当前无业务字段消费它，**先不建，等有真实消费点再建**。
3. **交通（transport）**：固定几种（飞机/火车/大巴/自驾），**建议 Selection**。`tour.line.send_traffic/end_traffic` 现在是 Char，应改为 Selection（或 `product.attribute` 若需要和 product 变体/价格联动）。交通方式在出团/核算里可能需要映射到成本类型，Selection 足够且类型安全。
4. **团队类型（team_type）**：0 数据、无消费点，**待 BA 确认业务语义后再定**，当前建议**直接删除**（不迁）。

> **原则**：字典的价值 = 有字段消费它 + 取值会变化。四类字典当前**既无消费、取值又固定**，属于「为迁数据而迁」的僵尸字典，应删除或降级为 Selection。

---

### 2.3 职务 — 应去 `hr.job`（当前只声明未实现）

**现状**：`tour_base_demo.xml` 中有一行注释 `<!-- 职务（items_11）已改由 hr.job 承载，不再作为 tour.base.item 的 duty 类型 -->`。但 grep 全库确认：**没有任何 tour_* 模块创建 hr.job 记录、没有 job_id 字段挂在 res.partner / hr.employee / tour.guide 上**（仅 account_move.py 里出现「职务分离」是内控合规标签字符串，与 hr.job 无关）。

**判定：❌ 只声明、未落地**。Odoo 原生 `hr.job`（职务/职位）正是「职务」的标准载体（含所属部门、招聘、薪资、招聘链接）。tour_resource 已 depends on `hr`，具备复用条件。

**改进建议（P1）**：

1. 在 tour_resource（或 tour_guide 层）为 `hr.employee` / `tour.guide` 加 `job_id = Many2one('hr.job')`（`hr.employee` 原生已有 job_id，tour.guide 可 related 过去）。
2. 把源 items_11 的 15 条「职务」迁为 `hr.job` 记录（一次性 SQL/迁移脚本）。
3. 删除 `tour.base.item` 里对「职务」的所有痕迹（本就没有 duty 类型，只需确认 demo 注释与文档一致）。

**迁移成本**：低（15 条职务 + 1 个字段），但需 HR/BA 确认「职务」挂在哪一层（hr.employee 还是 tour.guide）。

---

### 2.4 `tour.pay.way` 结算方式 — 与支付渠道重叠、语义混淆

**现状**：独立模型，`name + code + pay_type`（cash 现金 / transfer 银行转账 / credit 挂账月结 / prepaid 预付），7 条已迁。被 `tour.payment.claim.pay_way_id` 引用，help 文本写「签单/导游现付/公司现收等 7 种」——即**实际语义是「收付场景」，不是「结算方式」**。demo 数据 7 条的 `pay_type` **全部未填**（默认空）。

**关键冲突**：同时存在 `tour.pay.channel`（支付渠道，`channel_type`：bank_transfer/wechat/alipay/cash/other，挂 `fund_account_id + journal_id` 驱动会计分录）。两个模型都管「支付」，分类枚举却不一致、职责边界模糊：

| 维度 | tour.pay.way | tour.pay.channel | account 原生 |
|------|-------------|-----------------|-------------|
| 语义 | 收付场景（业务） | 资金渠道（会计落账） | — |
| 枚举 | cash/transfer/credit/prepaid（未用） | bank_transfer/wechat/alipay/cash/other | — |
| 会计能力 | 无 | ✅ fund_account + journal 路由 | account.payment.method / account.journal |

**判定：⚠️ 部分合规**。`tour.pay.channel` 是 **account.journal 的业务薄包装**（正确复用原生日记账路由），这个保留。但 `tour.pay.way` 存在三个问题：

1. **`pay_type` 混淆两类概念**：`cash/transfer` 是「支付方式」（≈ account.payment.method / tour.pay.channel），`credit/prepaid` 是「结算条款」（≈ account.payment.term）。混在一个字段里。
2. **与 `tour.pay.channel` 职责重叠**：cash/transfer 已被 channel_type 覆盖，pay_way 再造一套。
3. **`pay_type` 完全未使用**（demo 全空、代码只读 `pay_way_id.pay_type == 'credit'` 做签单判断，但数据没填 → 判断恒为假）。

**改进建议（P1）**：

| 方案 | 动作 | 适用 |
|------|------|------|
| **A（推荐）** | 保留 `tour.pay.way` 但**明确定位为「收付场景」业务字典**（签单/导游现付/公司现收/企业码支付…），`pay_type` 改为**标识「是否即时收付 / 是否挂账」的布尔或精简 selection**（如 `is_credit`），与 `tour.pay.channel`（资金渠道）解耦：场景决定「钱何时/谁付」，渠道决定「钱走哪个账户」 | 场景需用户维护时 |
| B | 若「收付场景」固定 7 种不变 → **降级为 Selection 常量**（放到 constants 或 tour_accounting），删 `tour.pay.way` 表 | 场景固定 |

> `credit`（挂账/月结）和 `prepaid`（预付）本质是**付款条件**，若后续要做账期/信用，应挂到 `account.payment.term`（原生）。短期不必引入，但 `pay_type` 不要再把「支付方式」和「结算条款」混装。

**迁移成本**：低（7 条数据，字段级调整）。

---

### 2.5 `tour.line.type` 线路分类 — 偏离设计（应评估 product.category）

**现状**：独立树模型（`_parent_store=True`，parent_id/parent_path/child_ids/line_ids），85 条已迁。**但 demo 数据 85 条全部扁平、无任何 parent_id**——树结构在迁移中丢失（源系统有 Layer 层级）。

**与设计文档的冲突**：TDS-DATA-001 §2.2 明确写 `tour.line.type` 应 `_inherit = 'product.category'`，§2.1 写 `tour.line` 应 `_inherit = 'product.template'`。**实现却把两者都做成了独立模型**（tour_product __manifest__ 虽 depends 'product'，但模型未继承 product）。

**判定：⚠️ 偏离设计文档**。这是「设计文档与实现分叉」的核心案例。两个方向必须二选一，不能悬着：

**改进建议（P0 决策）**：

| 方案 | 内容 | 收益 | 成本/风险 |
|------|------|------|-----------|
| **A（符合设计文档，推荐）** | `tour.line.type` 改为 `_inherit='product.category'`，`tour.line` 改为 `_inherit='product.template'`（服务型产品 service） | 免费获得：树形+父子联动、website 商品展示、sale 价格表、product.category 原生多语言/统计、与 account 收入科目的默认映射 | 🟡 中：需重写模型继承、迁移 85 分类 + 212 线路、tour.plan.line_id 等外键从 tour.line 改指 product.product 或保留 tour.line 作为 product 的扩展包装 |
| **B（保持独立，但修正设计文档）** | 维持 tour.line.type / tour.line 独立，**回改 TDS-DATA-001 使其与实现一致**，并补齐 85 条的树层级（parent_id） | 独立模型简单、无 product 依赖耦合 | 🟢 低：只改文档+补数据；但**永久失去 product.category/product.template 的原生能力**（网站展示、价格、销售集成） |

**架构判断**：旅行社「线路」本质是**可售产品（服务）**，且 SOUL.md 明确「能用标准功能就不自定义」。`product.template` 的 service 类型天然承载线路（名称/描述/价格/分类/图片/网站），`product.category` 天然承载树形分类。**当前独立模型是「当初为快速迁移而绕开 product」，属于短期走捷径**。

**但需权衡现实约束**：tour.line 已有 126 行独立逻辑（audit 状态机、发团/行程关联、价格体系），tour.plan 等大量模型已依赖 `tour.line` 这个 _name。若改 product.template，`line_id` 等外键、domain、报表都要动。

> **建议路线**：**短期 B（先补树层级 + 修正文档，止血），中期 A（线路逐步 product 化）**。P0 至少要做两件事：(1) 决策 A/B 并落文档；(2) 若 B，立即把 85 条线路分类的 parent_id 树结构补齐（否则「树形分类」名不副实，前端无法按层级展示）。

---

### 2.6 `res.partner.sup_type` 供应商类型 — 单一 selection 偏离设计

**现状**：`sup_type` selection 11 项（customer/ditch/hotel/meal/vehicle_comp/ticket/scenic/shop/insurance/self_fee/visa），挂在 tour_resource res.partner，单一选择。

**与设计文档的冲突**：TDS-DATA-001 §2.8 明确写「统一使用 res.partner，通过 `category_id`（联系人标签）区分供应商类型」，且给了 13 个标签映射（tour_customer/tour_ditch/…）。**实现却用单一 selection `sup_type`**。

**判定：⚠️ 偏离设计**，且单一选择有实际业务缺陷：

1. **一个供应商常是多重身份**（如「酒店+餐厅+购物店」），单选 selection 无法表达；`res.partner.category` 是 many2many 标签，天然多标签。
2. **绕过原生标签的过滤/分组/报表能力**（res.partner 的 tag_ids 搜索、分组、portal 展示）。
3. **重复定义**：`constants.SUP_TYPE`（11 项）与 `tour_resource/res_partner.py` 内联的 selection（11 项，完全一致）**重复维护，未 import**（DRY 违背，见 2.7）。

**改进建议（P1）**：

| 方案 | 动作 | 适用 |
|------|------|------|
| **A（符合设计文档，推荐）** | `sup_type` 迁移到 `res.partner.category_id`（tags），用 `tour_customer/tour_hotel/...` 标签区分；`sup_type` 字段降级为**派生/computed 字段**（从 category_id 取主标签）或直接删除，domain 里 `[('category_id','in',[...])]` 替代 `[('sup_type','=',...)]` | 需要多标签时（现实常见） |
| B | 若业务**强制**「一个供应商只属于一类」（单一主类型），保留 `sup_type` 单选作为「主类型」，但**额外加 category_id tags 做多标签**（主类型 + 辅助标签共存） | 单一主类型 + 辅助标签 |

> 判定依据：Odoo 原生对「供应商/客户分类」的标准做法就是 `res.partner.category`（tags），selection 是「绕开原生」的做法。SOUL.md「能用标准就不自定义」原则指向方案 A。

**迁移成本**：低（4122 个 partner，批量写 category_id + 建 11 个 category 记录；sup_type 改 computed）。

---

### 2.7 `constants.py` 集中管理 selection — 名存实亡 + 与真相矛盾

**现状**：`tour_base/models/constants.py` 集中定义 `BIZ_MODE(12)/SUP_TYPE(11)/PLAN_TYPE(4)/FROM_TYPE(3)/SEX(2)`。文件 docstring 自述「跨模块共用的 Selection 常量，单一事实来源」。

**判定：❌ 名存实亡**，且比「无用」更糟——**制造了第二个真相源，且与第一个真相矛盾**：

1. **无任何模块 import**：grep 全库，除 `tour_base/models/__init__.py` 的 `from . import constants` 外，**没有一处 `from .constants import ...` 或 `constants.XXX` 被业务代码引用**。5 个常量全是死代码。
2. **与实际字段矛盾**：`constants.BIZ_MODE` 是 **12 项**（docstring 说「收敛为 12 个规范取值」），但实际 `tour_plan.biz_mode` 是 **15 项**（多了别名码 '2'、'15'、'52'）。同一个「业务模式」出现两个不同版本，谁是对的不清楚。
3. **重复定义**：`SUP_TYPE`(11)、`PLAN_TYPE`(4)、`FROM_TYPE`(3)、`SEX` 都与各模块内联的 selection 字面量完全重复（tour_plan.py 内联 biz_mode/plan_type/from_type，tour_resource res_partner.py 内联 sup_type，tour_guide 内联 sex），**一份数据两处维护**。

**改进建议（P1）**：

| 步骤 | 动作 |
|------|------|
| 1 | **决策「单一真相源」到底是谁**：constants.py 还是各模块内联？Odoo 惯例是**内联**（selection 属于字段定义的一部分，字段和取值就近维护，跨模块复用才提常量）。 |
| 2 | **若保留 constants.py**：立即让各模块 import（删内联字面量，改 `from odoo.addons.tour_base.models.constants import BIZ_MODE`），并**修正 BIZ_MODE 为 15 项**（或明确「12 项规范 + 3 个别名」的映射关系，消除矛盾）。 |
| 3 | **若放弃 constants.py**（更贴近 Odoo 惯例）：删文件，各模块内联，跨模块真正复用的才抽常量。 |

> 关键：**「集中管理」本身不是坏实践，坏在「集中了却没人用、且内容与真相冲突」**。当前 constants.py 是最危险的中间态——它让阅读者误以为存在统一枚举，实际业务跑的是另一套。

---

### 2.8 `company_id` 多公司处理 — 不完整 + 反原生惯例

**现状**：`tour.base.item`、`tour.pay.way`、`tour.line.type`、`tour.pay.channel`、`tour.bank.account` 均加 `company_id = Many2one('res.company', default=self.env.company)`。但：

1. **无 ir.rule 多公司隔离规则**（对照：tour_accounting 有 `account_asset_category_multi_company_rule`、tour_budget 有 `budget_post_comp_rule`）。
2. **无 `_check_company` 校验**（跨公司引用不拦截）。
3. 字段加了 company_id，但视图未加 `groups="base.group_multi_company"`（对照 tour_budget/tour_accounting 视图都有该 groups）。

**判定：❌ 不完整**。`company_id` 字段本身**不产生任何隔离效果**——Odoo 的多公司隔离靠「`company_id` 字段 + `_check_company` + ir.rule（rule_multi_company）」三者配合。只加字段不加规则 = 伪隔离。

**更根本的问题**：**字典/主数据加 company_id 本身反 Odoo 原生惯例**：

| 原生字典 | 是否 company_id | 原因 |
|---------|----------------|------|
| `product.category` | ❌ 全局共享 | 分类是集团统一枚举，各公司共享 |
| `account.payment.method` | ❌ 全局 | 支付方式是标准枚举 |
| `uom.uom` | ❌ 全局 | 计量单位统一 |
| `account.payment.term` | ⚠️ 可选（`company_id` 可空） | 付款条件可共享或公司专属 |
| `res.partner.category` | ❌ 全局 | 标签全局 |

字典之所以是字典，就是因为它**全集团统一**。给房型/交通/结算方式加 company_id，会逼着每个公司重复维护同一套枚举，且不同公司字典值可能不一致，导致跨公司报表口径混乱。

**改进建议（P2）**：

1. **纯字典（房型/交通/结算方式/团队类型）→ 不加 company_id**（全局共享），或加但 `company_id=False`（空 = 全局），仅当某公司确实需要专属值时再挂。
2. **业务主数据（tour.bank.account 银行账户、tour.pay.channel 资金渠道）→ 保留 company_id，但补齐隔离机制**：加 `_check_company` + ir.rule，视图加 `groups="base.group_multi_company"`。银行账户/资金渠道是「公司级资产」，隔离合理。
3. 若项目实际**单公司**（从 SOUL 的 res.company 7 条看是多公司），则评估是否真需要多公司隔离，避免过度设计。

---

## 3. 汇总：改进路线图

### 3.1 按字典的「现状 → 合规 → 建议 → 成本 → 优先级」总表

| # | 字典 | 现状 | 合规 | 改进建议 | 迁移成本 | 优先级 |
|---|------|------|------|---------|---------|--------|
| 1 | `tour.base.item` | 万能字典 4 类 | ❌ | 拆解/删除；level_id 改独立 `tour.supplier.level` 或 category 标签 | 低 | **P0** |
| 2 | 房型 | 塞字典，实际 5 Integer 硬编码 | ⚠️ | 删除字典；房型保持 5 计数字段（如需扩展再上 product.attribute） | 低 | P1 |
| 3 | 团餐 | 塞字典，实际 project_task.meal_type selection | ⚠️ | 删字典；餐次=Selection 保留，餐型待消费点出现再建 | 低 | P1 |
| 4 | 交通 | 塞字典，实际 Char | ⚠️ | 删字典；send/end_traffic 改 Selection | 低 | P1 |
| 5 | 团队类型 | 塞字典，0 数据 | ❌ | 待 BA 确认，当前删 | 低 | P1 |
| 6 | 职务 | 仅注释声明 hr.job | ❌ | 落地：hr.employee/tour.guide 加 job_id，迁 15 条到 hr.job | 低 | P1 |
| 7 | `tour.pay.way` | 独立模型 + pay_type 4 类 | ⚠️ | 定位为「收付场景」，pay_type 改精简（is_credit），与 tour.pay.channel 解耦 | 低 | P1 |
| 8 | `tour.line.type` | 独立树模型（85 条扁平） | ⚠️ | **决策**：A 改 product.category / B 保持独立+补树层级+修文档；短期先补 parent_id | 中 | **P0** |
| 9 | `sup_type` | 单一 selection | ⚠️ | 迁 res.partner.category（tags），sup_type 改 computed 或删 | 低 | P1 |
| 10 | `constants.py` | 5 常量无人 import + 矛盾 | ❌ | 决策单一真相源；要么让模块 import+修正 BIZ_MODE 15 项，要么删文件 | 低 | P1 |
| 11 | `company_id` | 各字典都有字段无隔离 | ❌ | 纯字典去 company_id；业务主数据补齐 _check_company+ir.rule | 低 | P2 |

### 3.2 三个「决策点」（需协调人/BA 拍板）

1. **tour.line / tour.line.type 是否 product 化**（2.5 方案 A/B）——影响后续网站/销售/价格集成，是最大架构决策。
2. **供应商类型 sup_type 单选还是多标签**（2.6）——影响 partner 建模与 domain 写法。
3. **constants.py 去留**（2.7）——影响后续所有 selection 的维护约定。

### 3.3 核心原则（固化到规范）

1. **禁止万能字典**：一个模型一个语义，禁止用 `type/kind` selection 分诊装多类字典。
2. **字典三问**：取值固定且代码决定 → Selection；取值用户可维护且会增长 → 独立 M2O 模型；Odoo 已有 → 复用原生（product.category / hr.job / account.payment.term / res.partner.category）。
3. **单一真相源**：selection 要么内联、要么 constants 且全模块统一 import，**不允许「常量表 + 内联字面量」并存且内容矛盾**。
4. **字典不加 company_id**（全局共享）；业务主数据加 company_id 必须配 `_check_company` + ir.rule + 视图 groups。

---

## 4. 附：与既有设计文档的一致性声明

本评估发现 TDS-DATA-001（数据模型设计）与实现存在 **3 处分叉**，需后续同步修正：

| 设计文档原文 | 实现现状 | 本报告建议 |
|-------------|---------|-----------|
| §2.1 tour.line = product.template 扩展 | 独立模型 | 见 2.5（P0 决策） |
| §2.2 tour.line.type = product.category 扩展 | 独立模型 | 见 2.5（P0 决策） |
| §2.8 供应商类型用 category_id 标签 | sup_type selection | 见 2.6（P1） |

> 后续动作：无论 A/B 哪个方向，TDS-DATA-001 与实现必须收敛一致，避免「文档说一套、代码做一套」。
