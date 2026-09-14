# TDS-PROD-001 — 线路产品 product 化整体重写方案

> 文档编号：TDS-PROD-001
> 版本：v1.1（P0 已落地）
> 日期：2026-09-14
> 状态：已定稿（P0 模型重写已落地；P1 迁移脚本/P2 电商/P3 支付/P4 回归为待办阶段）
> 依据：BS-01 线路管理、BS-02 订单管理、TDS-DATA-001 数据模型设计、TDS-B2C-001 线上销售、现有代码 tour_product / tour_order / tour_website / tour_operation / tour_accounting
> 结论先行：**tour.line 采用委托继承 `_inherits = {'product.template': 'product_tmpl_id'}` 保留自建模型 + 1:1 委托 product.template**；分类改用原生 product.category；发团计划保留自建；电商走 website_sale 生成 sale.order 再桥接 tour.plan.reg。
>
> **实施进度**（2026-09-14）：P0 模型重写已落地（tour.line 已改 `_inherits`、tour.line.type 已删、85 条分类已迁 product.category、字段收敛完成）；P1 迁移脚本 `scripts/migrate_line_to_product.py` 已存在；P2 电商桥接、P3 支付对接、P4 回归 UAT 为待办。

---

## 一、现状盘点（代码 + 数据库实测，2026-09-14）

### 1.1 模块安装状态（`ir_module_module` 实测）

| 模块 | 状态 | 备注 |
|------|------|------|
| `sale` / `sale_management` | ✅ installed | 销售模块在装，`sale.order` 可用 |
| `website` / `website_sale` | ✅ installed | **电商链路可用**（B2C 购物车/结账/支付/发票） |
| `purchase` / `delivery` | ✅ installed | 采购、配送在装（未被 stock 拖累） |
| `account` / `analytic` | ✅ installed | 财务 + 分析账户在装 |
| `product` | ✅ installed | 产品基类在装 |
| `stock` | ❌ uninstalled | 已卸载（符合「不碰库存」） |

> 关键结论：`website_sale` 已装，B2C 电商销售的前置条件全部满足，无需新装标准模块。这与 TDS-B2C-001 附注「website_sale 已安装（容器实测）」一致，但彼时决策是「线下付款、不用购物车」；本次方案升级为「真正启用 website_sale 电商」。

### 1.2 数据量实测

| 表 | 记录数 | 说明 |
|----|--------|------|
| tour.line | **213** | 线路产品 |
| tour.line.type | **85** | 分类，**实测 parent_id 全空（0 条有父级）→ 完全扁平** |
| tour.departure | **11119** | 发团计划 |
| tour.line.detail | **803** | 行程明细 |
| tour.plan | 86926 | 团队订单 |
| tour.plan.reg | 86759 | 订单报名 |
| product.template / product.product | 7 / 7 | 均为 Odoo 自带 service demo（餐食/里程/费用等），`type='service'` |
| product.category | 4 | 原生分类仅 demo 数据 |

### 1.3 谁引用 tour.line（决定「不能断」的边界）

**直接外键指向 tour.line（必须保持 id 不变）**：

| 引用方 | 字段 | ondelete | 所属模块 |
|--------|------|----------|----------|
| tour.departure | line_id | cascade | tour_product |
| tour.line.detail | line_id | cascade | tour_product |
| tour.plan | line_id | **restrict, required** | tour_order |
| crm.lead | line_id | (默认 set null) | tour_order |
| tour.plan.account | line_id | related('plan_id.line_id') store | tour_accounting |
| tour.dunning | line_id | related('plan_id.line_id') store | tour_accounting |

**tour.line.line_type_id → tour.line.type**（分类，`required=True`）；`tour.line.type.line_ids` 反向。

**关键洞察**：财务 / 订单 / 计调三大链路的落地锚点**全部是 `tour.plan`，不是 tour.line 本身**：

```
tour.line ──(line_id)──▶ tour.plan
                             ├─ tour.plan.reg（报名，plan_id）
                             ├─ project.project（1:1 tour_plan_id）→ project.task（计调）
                             ├─ account.analytic.account（tour_plan_id，一团一核算）
                             ├─ tour.plan.account（单团核算，plan_id）
                             ├─ tour.payment.claim（收款认领，plan_id）
                             └─ account.move（记账，tour_plan_id）
```

→ 只要 `tour.line` 的**表名与 id 不变**，`tour.plan.line_id` 这条唯一主 FK 不断，财务/订单/计调全链路自动保持。这是本方案选型的第一约束。

---

## 二、核心架构决策

### 2.1 tour.line 与 product 的关系：推荐「委托继承 `_inherits`」（方案 A′）

先厘清 Odoo 三种继承语义（本决策的关键）：

| 机制 | 写法 | 效果 | 是否适合本场景 |
|------|------|------|----------------|
| 经典继承 | `_inherit='product.template'` + `_name='tour.line'` | tour_line 表 `INHERITS(product_template)`，**tour.line 行不在 product_template 表里**，`product.template` 查询看不到 tour.line 行 | ❌ 致命：product.product 的 `product_tmpl_id` FK 指向 product_template，无法指向 tour.line；website_sale 卖不了 |
| 原型扩展 | `_inherit='product.template'`（不加 `_name`） | 把旅行字段直接加到 product.template 上，**删除 tour.line 模型**，全系统改引用 product.template | ⚠️ 最「合一」但迁移最大（改 6 处 FK + 全代码 `'tour.line'`），财务/订单/计调需全量回归 |
| **委托继承** | `_inherits={'product.template':'product_tmpl_id'}` | tour.line 保留自己的表与 id，新增 `product_tmpl_id` 1:1 指向 product.template，字段自动代理 | ✅ 标准范式（product.product 对 product.template 即如此），零 FK 改动，电商即用 |

**推荐：方案 A′ = `_inherits` 委托继承。** 它同时吸收任务中「方案 A（线路即产品）」与「方案 B（保留自建 + 关联 product）」的长处：

```python
# tour_product/models/tour_line.py（重写后）
class TourLine(models.Model):
    _name = 'tour.line'
    _description = '线路产品（委托 product.template）'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'product.template': 'product_tmpl_id'}
    _order = 'sequence, name'

    product_tmpl_id = fields.Many2one(
        'product.template', string='产品模板', required=True,
        index=True, ondelete='cascade', auto_join=True)
    # 旅行专属字段保留在 tour.line（见 §3 字段映射）
    # 电商/标准字段经委托代理：line.name / line.categ_id / line.list_price /
    #                          line.default_code / line.is_published / line.image_1920 ...
```

**推荐理由（按决策权重排序）**：

1. **不破坏下游（决定性）**：tour.line 表名、id、`line_id` 主 FK 全部不变。11119 发团、803 行程、86926 团、86759 报名、计调 project、财务 analytic 全链路无需改动即可继续工作。方案 A*（原型扩展删除 tour.line）要做到「不破坏」需迁移全部外键 + 全量回归，风险最高。
2. **Odoo 实施标准**：`_inherits` 委托是官方原生范式（`product.product` 委托 `product.template`、`event.ticket`/`hr.expense` 同样用 delegation）。「线路 = 一种 service 产品」用 delegation 表达最地道。
3. **电商就绪**：每个 tour.line 对应一个真实的 product.template（`type='service'`），website_sale 目录页/商品页/购物车/结账/开票直接可用；product.product 变体自动生成（见 §4.2）。
4. **收敛而非分裂**：方案 B（裸 1:1 M2O 不委托）没有字段代理，name/价格/分类/上架状态需手工双向同步，易漂移、增维护面。`_inherits` 自动代理，零同步代码。
5. **迁移成本最低**：只需「为每条 tour.line 建一个 product.template 并回填 product_tmpl_id」+「删除 tour.line 上与 product.template 重复的字段」，不移动任何下游数据。

**为什么不选字面「方案 A（`_inherit='product.template'`）」**：经典继承会让 tour.line 行物理上只存在于 `tour_line` 子表，`product.template` 查询（website_sale 商品目录、product.product 的 `product_tmpl_id` 外键）看不到这些行——线路根本卖不出去，违背目标。若想要「字段真正合一、线路就是 product.template」，正解是「原型扩展 product.template + 删除 tour.line」（方案 A*），但它把「不破坏财务/订单/计调」的成本推到最高。**除非决策层明确接受全量回归，否则不取 A*。**

---

### 2.2 线路分类：改用原生 product.category（废弃 tour.line.type）

**推荐：迁移到 product.category，删除 tour.line.type。**

理由：
1. tour.line.type 虽模型自带 `_parent_store/parent_id/child_ids`，但**数据 85 条全扁平（实测 0 条有父级）**，自建树形没被用起来；换成原生 product.category 直接获得树形、`parent_path`、面包屑、website_sale 分类页/SEO 能力，零额外开发。
2. product.template 已有 `categ_id`（Many2one product.category），委托继承后 `line.categ_id` 直接可用，website_sale 的分类过滤/URL 结构原生支持。
3. 收敛模块：少一个自建分类模型，符合「能用标准功能就不自定义」。

迁移要点（详见 §6）：
- 85 条 tour.line.type → 85 条 product.category，1:1 映射 `name/code/sequence/active/description`，`parent_id` 全空（数据本就扁平，后续再人工建树）。
- 生成 id 映射表 `{tour_line_type_id → product_category_id}`，用于回填 tour.line.categ_id。
- 移除 `tour.line.line_type_id`、`tour.line.type` 模型及其 views/menu/access。若需保留兼容别名（短期过渡），可在 tour.line 上加 `line_type_id = related('categ_id')` 只读代理字段，但不推荐长期保留。

---

### 2.3 发团计划 tour.departure 与 product 的关系：保留自建，不拆变体

**推荐：tour.departure 保留自建模型，电商按「线路 = 一个可售 product」上架，发团日期作为「下单必选项」而非 product.product 变体。**

理由：
1. **库存形态不符**：tour.departure 的核心是「日期 + 动态余位（booked_seats/remain_seats）+ 五档价（成人/儿童/老人/学生/婴儿）」。若每班期做成一个 product.product 变体，则 11119 班期 → 上万变体，且「按日期选变体」不是 Odoo 变体选择器（属性组合下拉）能优雅表达的——变体适合「尺码/颜色」这类离散静态属性，不适合「连续日期 + 实时余位」。
2. **价格体系不符**：product 原生只有 `list_price`（单一单价）。线路是「五档价 × 班期浮动价」，落在 tour.departure（班期五档价）回退 tour.line（模板五档价）。这正好映射 product 语义：**product.template = 线路模板（list_price=成人价），tour.departure = 班期（变体价 + 库存）**。保留自建 departure 是行业（旅游电商）通行做法。
3. **复用现有链路**：`create_online_reg` 的「选班期 → 校验余位 → 回写 booked_seats」逻辑全部保留不动。

**B2C 下单时如何选发团日期**（详见 §4.3）：
- 商品页在「加入购物车」前，用自定义 widget 让用户选择 `tour.departure`（只列 `state='published'` 且 `remain_seats>0` 且 `start_date>=today` 的班期）。
- 选中班期作为 `sale.order.line` 上的扩展字段 `departure_id` 写入购物车行，服务端在「购物车行/结账/确认」各环节重校验余位。
- 单价 = `departure.get_online_prices()` 按五档人数计算，服务端重算，前端只读展示。

---

## 三、目标数据模型与字段映射

### 3.1 字段归属原则

| 归属 | 内容 | 理由 |
|------|------|------|
| **product.template（委托代理）** | name、default_code、categ_id、list_price、type='service'、is_published/website_published、image_1920、website_description、taxes_id、sale_ok、active、company_id | 电商/标准字段，website_sale 依赖 |
| **tour.line（旅行专属，保留自建）** | day_num/night_num、行程信息、五档价（child/old_man/student/baby）、费用包含/不含、行程安排/特色/购物/自费/温馨提示/注意事项、地接社、导游分成、audit_state、is_special/is_abroad、help_code、sequence、统计字段 | 旅行社业务字段，电商不直接消费 |
| **tour.departure（保留）** | 班期日期、余位、班期五档价、state | 排期/库存维度 |

### 3.2 字段映射表（tour.line 重写后）

| 现状 tour.line 字段 | 去向 | 目标字段 | 说明 |
|---------------------|------|----------|------|
| name | **删除，委托** | product.template.name | 线路名 = 产品名 |
| code | **删除，委托** | product.template.default_code | 线路编号 |
| active | **删除，委托** | product.template.active | 启用 |
| line_type_id | **删除，迁移** | product.template.categ_id | 分类 → product.category |
| adult_price | **删除，委托** | product.template.list_price | 成人价 = 模板销售价 |
| child_price / old_man_price / student_price / baby_price | 保留 tour.line | 同名字段 | 四档价（product 无此概念） |
| day_num / night_num | 保留 tour.line | 同名字段 | 天数/夜数 |
| send_place / end_place / from_* / to_* / *_traffic | 保留 tour.line | 同名字段 | 行程地理信息 |
| fee_include / fee_exclude | 保留 tour.line | 同名字段 | 费用包含/不含 |
| srv_text / details_rich / feature_rich | 保留 tour.line（可选另映射 website_description） | 同名字段 | 富文本；website_description 可在迁移时由 srv_text/feature_rich 生成 |
| shopping_info / self_paid_item / warm_hint / attentions | 保留 tour.line | 同名字段 | 购物/自费/提示 |
| dj_supplier_id / guide_share_rate / guide_premium | 保留 tour.line | 同名字段 | 地接社/导游分成 |
| audit_state / is_special / is_abroad | 保留 tour.line | 同名字段 | 审核/特殊/境外 |
| help_code / short_name / sequence | 保留 tour.line | 同名字段 | 检索/排序 |
| company_id / user_id / department_name | 保留 tour.line（company_id 也可委托 product.company_id） | 同名字段 | 归属 |
| departure_count / detail_count | 保留 tour.line | 同名字段 | 统计 compute |
| （新增）product_tmpl_id | 新增 | Many2one product.template | 委托主键，required/cascade/auto_join |
| （新增）website_published 语义 | 委托 product.is_published | — | 上架开关；与 audit_state='approved' 双条件控制前台可见 |

> 注：`sale_ok`/`is_published` 由 sale/website 模块挂在 product.template 上。为保持 tour_product 轻量（不引入 website 依赖），这两个字段的**启用与上架联动逻辑**放在 tour_website（已依赖 website）或新增的 tour_website_sale 集成里处理（见 §5），tour_product 只做 `_inherits` 委托（依赖 `product` 即可，`product` 已装）。

### 3.3 委托后读写兼容性

委托继承自动为 tour.line 代理 product.template 的字段，**现有代码里 `line.name`、`line.active`、`line.adult_price→list_price` 等读写无需改动**（读走代理、写穿透到 product.template）。需要显式改的点：
- `line.line_type_id` 引用 → `line.categ_id`（tour_website 控制器 `tour_list` 的分类筛选、视图 filter）。
- `line.adult_price` 读 → `line.list_price`（tour_website `website_price_map`、`get_online_prices` 回退价）。

---

## 四、website_sale 电商链路设计

### 4.1 总览：两条入口，一个下游

```
【入口1 · 电商标准链路（新增）】               【入口2 · 轻量报名（现有）】
线路 product.template(service, is_published)   tour.line 详情页（现有 /tours/<id>）
        │ 选班期 departure_id（自定义 widget）          │ 选班期 departure_id
        ▼                                              ▼
product.product ──▶ sale.order.line（+departure_id/五档人数）   create_online_reg()
        │                                              │
        ▼                                              │
     sale.order（购物车/结账/在线支付/portal 客户）       │
        │ 确认/支付成功 桥接                             │
        └──────────────┬───────────────────────────────┘
                       ▼
           _create_plan_reg_from_order()（共享服务方法：校验余位→建/定位团→建报名→回写余位）
                       ▼
              tour.plan + tour.plan.reg（唯一业务主数据 + 唯一财务口径）
                       ▼
        财务（收款认领/收入确认/发票/单团核算）+ 计调（project.task）+ 订单（并团/状态机）
```

### 4.2 核心决策：website_sale 生成 sale.order，不直接生成 tour.plan

**推荐：电商下单生成 `sale.order`（+ 行扩展字段），订单确认/支付后经桥接方法生成 `tour.plan.reg`/`tour.plan`。**

理由：
1. website_sale 的购物车、结账、在线支付、开票、portal「我的订单」全部依赖 sale.order + account 标准链路。放弃 sale.order 等于放弃 website_sale 的核心价值。
2. `sale.order` 语义 = 销售单；`tour.plan` 语义 = 团期计划（并团/计调/单团核算）。两者是不同层，不应互相替代。sale 已装且 tour_accounting 已扩展 sale.order（credit_limit 等）。
3. **财务唯一口径**：`tour.plan` 承载 BS-10/BS-11/BS-14 已建好的「收款认领 tour.payment.claim + 收入确认 action_recognize_revenue + 差额征税 + 单团核算 tour.plan.account」。电商 sale.order **只做前台销售/在线收款入口，不独立建账**——在线支付成功的收款在 tour.plan 层生成收款认领（复用现有），发票走现有 tour_invoice（BS-12）。避免「sale 一套账 + tour 一套账」的重复记账与对账混乱。

### 4.3 sale.order.line 扩展（五档价 + 班期）

```python
# 新增模块 tour_website_sale（或并入 tour_website，见 §5）
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'
    departure_id = fields.Many2one('tour.departure', string='发团班期',
                                   index=True, ondelete='set null')
    adult_num = fields.Integer('成人数', default=1)
    child_num = fields.Integer('儿童数', default=0)
    old_man_num = fields.Integer('老人数', default=0)
    student_num = fields.Integer('学生数', default=0)
    baby_num = fields.Integer('婴儿数', default=0)
    # 单价/小计：onchange 依据 departure.get_online_prices() 服务端重算，
    # 前端只读展示「成人价 ¥X × N」，禁止客户端传价
```

- 商品页 widget：选择班期（可报名班期列表）→ 填五档人数 → 加入购物车。
- 购物车/结账：`departure_id` 随行保留，服务端在「加购、改量、结账校验、确认」各环节重校验 `remain_seats`（防超卖，复用 tour.departure `@api.constrains booked_seats<=seats` 兜底）。
- 金额：单价从 `departure.get_online_prices()` 派生，五档价 × 人数 = 行小计。

### 4.4 桥接：sale.order → tour.plan.reg

**与现有 create_online_reg 的关系：合并（抽取共享服务方法），而非替代。**

将现有 `create_online_reg` 的「校验 → 建/定位团 → 建报名 → 回写余位 → 汇总团金额」核心逻辑抽取为共享方法 `_create_plan_reg_from_order(self, line, departure, 人数, 联系人, 客人证件, source)`：
- `create_online_reg`（入口2，无登录轻量报名）→ 调共享方法，`from_type='6'`（线上官网），线下付款。
- `sale.order` 确认/支付成功（入口1，电商）→ 调共享方法，`from_type='6'`（或新增 '7' 电商渠道），并在 `sale.order` 与 `tour.plan.reg`/`tour.plan` 之间回写关联（如 `reg.sale_order_id`），在线收款。
- 两条路径共享同一套余位校验、五档价、建团、余位回写，保证不重复造轮子、财务口径一致。

**演进预留**：入口2（无登录）转化率高，短期保留；P2/P3 可让 `create_online_reg` 内部也转成一个单行 sale.order（走统一购物车/支付），实现单一路径收敛。

---

## 五、模块规划（收敛）

| 模块 | 变更 | 依赖变更 |
|------|------|----------|
| `tour_product` | tour.line 改为 `_inherits={'product.template':'product_tmpl_id'}`；**删除 tour.line.type** 及 line_type_id；分类视图改用 product.category | 依赖保持 `product`（已装），不新增 website/sale 依赖 |
| `tour_website` | 控制器分类筛选 `line_type_id`→`categ_id`；`adult_price`→`list_price`；保留 create_online_reg 并抽取共享方法 | 保持 `website/portal` |
| **新增 `tour_website_sale`**（推荐独立薄模块） | sale.order.line 扩展（departure_id/五档人数）、商品页班期 widget、sale.order→tour.plan.reg 桥接、上架联动（audit_state+is_published）、在线支付收款认领回写 | 依赖 `sale`、`website_sale`、`tour_product`、`tour_order`、`tour_website` |

> 收敛说明：把电商桥接独立成 `tour_website_sale` 而非塞进 tour_website，理由是 tour_website 当前是「无登录轻量报名」定位（无 sale 依赖）；电商引入 sale/website_sale 依赖与支付逻辑，独立模块便于演进与替换（如后续接聚合支付走 tour_api）。若决策层倾向「少一个模块」，也可并入 tour_website（给它加 sale/website_sale 依赖），代价是轻量报名模块被迫带上 sale 栈。**默认推荐独立 `tour_website_sale`。**

---

## 六、数据迁移方案

### 6.1 迁移总原则

- **不移动下游数据**：tour.plan / tour.plan.reg / tour.departure / tour.line.detail / project.task / analytic / account.move 全部原位不动（id 不变）。
- **只做三类操作**：① 建 product.category（85）；② 建 product.template（213）并回填 product_tmpl_id；③ 删除 tour.line 上与 product.template 重复的字段列（数据已 copy 走）。
- 迁移用幂等脚本（`scripts/migrate_line_to_product.py`），分步可重入，每步打印影响行数与校验结果。

### 6.2 迁移步骤（严格顺序）

**阶段 M1：分类迁移**
1. 读 85 条 tour.line.type → 建 product.category（`name/code/sequence/active/description` 映射，`parent_id` 置空）。
2. 生成映射 `{tour_line_type_id → product_category_id}`（内存 dict 或临时表）。
3. 校验：product.category 计数 = 85，无重名丢失。

**阶段 M2：产品模板创建 + 回填委托键**
4. 加列 `tour_line.product_tmpl_id`（新模型字段引入后由 ORM 建列）。
5. 对每条 tour.line 创建 product.template：
   - `type='service'`、`name=tour_line.name`、`default_code=tour_line.code`、`list_price=tour_line.adult_price or 0`、`categ_id=映射后的 product_category`、`active=tour_line.active`、`is_published=(audit_state=='approved')`、`website_description`（可选，由 srv_text/feature_rich 生成）、`sale_ok=True`。
6. 回填 `tour_line.product_tmpl_id`。
7. 校验：product.template 新增 213 条（总 220 含原 demo）；每条 tour.line 有且仅有一个 product_tmpl_id；抽样比对 name/code/价格一致。

**阶段 M3：字段收敛**
8. 删除 tour.line 重复字段列（name/code/active/line_type_id/adult_price）——委托后读写已指向 product.template，旧列数据已 copy 走，可 drop。
9. 删除 tour.line.type 模型、views、menu、access、demo 引用。
10. 更新代码引用：`line_type_id`→`categ_id`、`adult_price`→`list_price`（tour_website 控制器、视图 filter、website_price_map、get_online_prices 回退）。

**阶段 M4：全链路回归**
11. 验证：tour.plan.line_id / tour.departure.line_id / crm.lead.line_id 外键全部仍解析到原 tour.line.id；`tour.plan.reg` 报名、计调 project.task、单团核算 tour.plan.account、收入确认、收款认领端到端跑通（复用 scripts/uat_full_flow.py 扩展）。

### 6.3 迁移前备份与回滚

- 迁移前 `pg_dump` 全量快照（含 tour_line、tour_line_type、product_template、product_category）。
- 脚本事务化：M1/M2 单事务提交，失败自动回滚；M3 删列在最后单独提交并留备份表 `tour_line_backup`。

---

## 七、不破坏财务/订单/计调的保障清单

| 链路 | 现状锚点 | 迁移后是否受影响 | 保障 |
|------|----------|------------------|------|
| 订单 tour.plan / tour.plan.reg | plan.line_id → tour.line | ✅ 不受影响（id 不变） | 主 FK 不动 |
| 计调 project.task | project.project.tour_plan_id → tour.plan | ✅ 不受影响 | 经 tour.plan 间接，不碰 tour.line |
| 财务 analytic 单团核算 | tour.plan.analytic_account_id / tour.plan.account.plan_id | ✅ 不受影响 | 经 tour.plan 间接 |
| 收款 tour.payment.claim | plan_id → tour.plan | ✅ 不受影响 | 经 tour.plan 间接 |
| CRM 转团 crm.lead.line_id | → tour.line | ✅ 不受影响 | id 不变 |
| 线上报名 create_online_reg | line/departure → tour.line/tour.departure | ✅ 逻辑保留 | 抽取共享方法，入口2 行为不变 |
| 线路分类 | line.line_type_id → tour.line.type | ⚠️ 字段迁移 | 迁移到 categ_id，代码同步改 |
| 线路价格 | line.adult_price | ⚠️ 字段迁移 | 迁移到 list_price，代码同步改 |

**结论**：唯一需要「动」的是 tour.line 自身（字段迁移 + 委托键），下游六条链路（订单/报名/计调/财务/收款/CRM）全部经 tour.plan 或保持 id 不变，无外键破坏。

---

## 八、分阶段实施步骤

| 阶段 | 内容 | 产出 | 风险 |
|------|------|------|------|
| P0 模型重写 | tour.line 改 `_inherits`；删 tour.line.type → 用 product.category；字段映射落地 | tour_product 重写 | 中（需改视图/menu/access） |
| P1 迁移脚本 | scripts/migrate_line_to_product.py（M1-M3）+ 备份回滚 | 迁移脚本 + 校验 | 中（数据一致性） |
| P2 电商桥接 | 新增 tour_website_sale：sale.order.line 扩展、班期 widget、桥接方法、上架联动 | tour_website_sale | 中 |
| P3 支付/收款对接 | 在线支付成功 → 收款认领回写 tour.plan（复用现有）；发票走 BS-12 | 支付闭环 | 高（财务口径） |
| P4 回归 + UAT | 全链路端到端（报名/下单/计调/核算/报表） | UAT 报告 | 低 |

**建议先 P0+P1（模型 + 迁移）单独上线验证「不破坏」，再 P2/P3 叠加电商，降低爆炸半径。**

---

## 九、风险与对策

| # | 风险 | 等级 | 对策 |
|---|------|------|------|
| 1 | `_inherits` 委托的字段代理与既有 tour.line 同名列冲突（name/active 等双列） | 高 | M3 前先删 tour.line 重复列再启用委托，或迁移期用 `related` 兜底；迁移脚本单事务 + 全量校验 |
| 2 | 分类迁移 85→product.category 时 code 重复 / 名称冲突 | 中 | 迁移前查重；code 冲突加后缀并记录映射，不静默覆盖 |
| 3 | 五档价 + 班期浮动价在 website_sale 购物车的金额一致性 | 中 | 单价全部服务端重算，前端只读；结账/确认二次校验余位与价格快照 |
| 4 | 电商 sale.order 与 tour.plan 财务两套账并存导致重复记账 | 高 | 明确「sale.order 只做销售/在线收款入口，财务唯一口径在 tour.plan」；在线收款经桥接回写 tour.payment.claim，不在 sale 层独立出账 |
| 5 | 余位超卖（电商并发 > 轻量报名并发） | 中 | 班期行 `FOR UPDATE` 锁 / `booked_seats<=seats` constrains 兜底；共享校验方法 |
| 6 | 经典继承误用（若实现者误用 `_inherit` 而非 `_inherits`） | 高 | 方案评审重点标注；代码 review 强制核对 `_inherits` |
| 7 | 上架状态与审核状态脱节（is_published 与 audit_state） | 低 | 上架联动放 tour_website_sale：`is_published` 仅在 `audit_state='approved'` 且 `active` 时可开 |

---

## 十、待评审确认项

1. 分类 `line_type_id` 是否接受「迁移即废弃」（不留只读兼容别名）——默认接受。
2. `adult_price` 是否同意映射为 product `list_price`（语义从「五档之一」升级为「模板标准销售价」）——默认同意。
3. 电商模块是否独立成 `tour_website_sale`（默认）还是并入 tour_website。
4. 在线支付渠道范围（微信/支付宝/其他）与是否 P2 接聚合支付——影响 P3 工作量。
5. 是否接受「方案 A*（彻底合一、删 tour.line）」作为备选——默认不取（全量回归成本高）。

---

## 附：决策速览

| 决策点 | 结论 |
|--------|------|
| tour.line ↔ product 关系 | **委托继承 `_inherits={'product.template':'product_tmpl_id'}`（方案 A′）** |
| 线路分类 | **改用原生 product.category，废弃 tour.line.type** |
| 发团计划与 product | **保留自建 tour.departure，不拆 product.product 变体；班期作为下单必选项** |
| 电商下单产物 | **website_sale 生成 sale.order，桥接生成 tour.plan.reg/tour.plan** |
| 与 create_online_reg 关系 | **合并（抽取共享方法），入口2 保留为轻量报名** |
| 财务口径 | **唯一口径在 tour.plan；sale.order 只做销售/在线收款入口** |
| 模块 | tour_product 重写 + 新增 tour_website_sale（默认） |
