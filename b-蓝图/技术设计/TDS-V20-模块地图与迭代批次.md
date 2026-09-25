# TDS-V20 · 旅行社行业应用模块地图与迭代批次

| 项 | 值 |
|----|----|
| 文档编号 | TDS-V20 |
| 状态 | 待评审（2026-09-25 起草） |
| 上游 | `b-蓝图/产品设计/PRD-V20-旅行社行业应用产品规划.md` |
| 取代 | `TDS-模块划分.md`（14 模块/292 人天，v19 口径，仅存档） |
| 底座 | tour20（`odootour:20.0-a2`，84 已装模块：core + om 全家桶 + l10n_cn，清单见 `c-系统实现/odootour/ODOO_PIN.md`） |

> 模块前缀统一 **`ta_*`**（travel agency），与参考代码 `tour_*` 彻底区隔；所有模块**完全新写**，不复制旧代码。版本格式 `20.0.x.y.0`。

---

## 1. 模块总览

### 批 1 · 核心闭环（MVP）

```
ta_base ──┬── ta_route ── ta_order ──┐
          ├── ta_dispatch ───────────┼── ta_finance（收款认领 + 单团核算）
          └── ta_guide ──────────────┘
```

| 模块 | 职责 | 依赖 | 关键模型草案 | 退出标准（DoD） |
|------|------|------|-------------|----------------|
| `ta_base` | 主数据与公共件：业务模式码（15 项新命名+映射表）、结算方式、票据类型、角色组与菜单骨架、res.config.settings 汇总 | `base`, `mail` | `ta.biz.mode`, `ta.settings.mixin` | 模式码字典可配置停用；权限组安装即用，四眼拦截有单测 |
| `ta_route` | 线路产品（行程明细、多价格体系）、班期（发团计划、名额、成团线）、并团（散客/班期并实团） | `ta_base`, `product` | `ta.route`, `ta.route.trip`, `ta.departure`, `ta.departure.merge` | 建线路→开班期→报名中/成团状态机全通；余位与成团线校验有测试 |
| `ta_order` | 团队/散客订单报名、名单、报价→应收计划（分期期次）、订单状态机 | `ta_route` | `ta.order`, `ta.order.line`(名单), `ta.receivable.plan` | 报价生成应收计划正确；订单↔班期占用/释放一致，幂等 |
| `ta_dispatch` | 计调：资源预订条目（车/房/餐/票/地接）、导游领队安排、成本预算确认生成应付 | `ta_order`, `purchase`(core) | `ta.dispatch.item`, `ta.vendor.bill.link` | 条目确认→供应商账单草稿链路通；取消/变更留痕 |
| `ta_finance` | 收款登记（银行流水导入）、三步认领与审核、自动核销应收、单团损益归集（毛利口径按 BS-19 裁定） | `ta_order`, `om_account_bank_statement`, `om_account_accountant`, `l10n_cn`, `account` | `ta.bank.line`, `ta.payment.claim`, `ta.team.pnl` | 登记≠认领≠审核拦截生效；审核后应收自动核销、单团已收/未收回写；profit 口径单测覆盖正负与含税开关 |
| `ta_guide` | 导游借款申请-审批-发放-逾期提醒、移动端报账（费用+票据）、佣金单计算、税后净额冲抵借款、导游对账确认 | `ta_finance`, `hr`(core), `portal` | `ta.guide.loan`, `ta.guide.expense`, `ta.guide.commission` | 借款入账挂其他应收款；报账审核计入团成本；冲抵按 AC-18 有测试；对账确认闭环（19 端缺失项，批 1 收口） |

### 批 2 · 内控与税务纵深

| 模块 | 职责 | 依赖 | 退出标准 |
|------|------|------|----------|
| `ta_shopping` | 购物点、游客购物记录、返佣分成规则（旅行社/导游分成比例）、佣金单联动、退单红字与个税抵扣提示 | `ta_guide` | 返佣→分成→并入佣金结算全链可跑；退单口径有单测 |
| `ta_taxdiff` | 差额征税底稿：可扣除成本清单、剔除额计算、与 fp（财税位置）联动出申报辅助报表 | `ta_finance` | NFR-1 强制：换算方向单测；底稿与总账勾稽平衡 |
| `ta_approval` | 三段审核（计调→财务→管理层）对订单确认/费用/结算的分级审核流，级数在 settings 可调 | 各业务模块 | 越级提交被拦；审核轨迹完整 |
| `ta_report` | 单团利润多维报表、现金看板、班期上座率 | 批 1 全部 | 报表数与业务库口径一致抽检通过 |

### 批 3 · 长尾（仅立项，不排期）

游客在线自助（BS-17/18 口径，portal 扩展）、多币种、期初建账向导产品化（BS-16）、批量导入工具化、SaaS 化评估（按 PRD-V20 §5 三原则复查）。

## 2. 迭代批次计划与验收演示

**批 1 目标**：一家新旅行社半天开库装模块，跑通一条完整业务线。**人天量级估算**：ta_base 10–14、ta_route 18–22、ta_order 16–20、ta_dispatch 12–15、ta_finance 20–25、ta_guide 15–18，集成测试与部署脚本 8–10，合计 **约 100–124 人天**（对照 v19 全量 292 人天，收缩到闭环）。

**批 1 演示场景线（验收脚本）**：
1. 建"XX 五日精华游"线路 → 开 3 个班期，设成人/儿童/单房差价格；
2. 某企业 20 人团队报名（模式码：团队输单）+ 4 名散客报同一班期（散客单组）；散客并团并入实团；
3. 银行流水导入 3 笔到账 → 出纳登记 → 业务员拆分认领（1 笔到账拆给两团）→ 会计审核 → 验证应收自动核销、团汇总已收/未收正确；
4. 计调录入用车/用房/地接条目并确认 → 生成供应商账单草稿 → 过账；
5. 导游借支备用金 → 审批发放 → 移动端报 3 笔带团费用（含 1 笔跨团错配被拦截）→ 费用计入本团成本；
6. 行程结束"结算完成" → 打开单团损益：验证 `profit = income − cost÷(1+r)`，切换含税开关观察 `profit_tax_incl` 且无双重扣减；
7. 导游佣金单生成 → 税后净额冲抵借款 → 对账确认；
8. 全程穿插 NFR 检查：重复点击认领审核不产生第二张凭证（幂等）、取消班期无孤儿订单（级联校验）、cron 带锁。

**批 2 演示场景线**：购物店返佣入账→导游分成 6:4→并入佣金单→退单红字与个税抵扣提示；差额征税底稿与 11 月申报表勾稽；三段审核越级拦截。

## 3. 工程约定

| 项 | 约定 |
|----|------|
| 开发目录 | `c-系统实现/odootour/modules/ta_*`（git 管理）；经 rsync/挂载进入 `~/odoo20tour/cust_addons/ta_*` 供容器加载（沿用现挂载链路，不动 compose） |
| 装载纪律 | 影子库先行（NFR-5）：`tour20` 之外建 `tour20_dev`，任何 `-i/-u` 先影子后正式；验收后库内模块清单变更同步 `ODOO_PIN.md` |
| 参考代码 | `tour_*`/addons20 只读参考，禁止复制粘贴迁移；引用其规则时在 commit message 注明"规则出处 BS-xx/旧模块:文件" |
| 依赖红线 | 不自建第二套总账/凭证（一律落 `account.move`）；不用 om_hr_payroll 做佣金发放（撞名风险已记录于 ODOO_PIN.md，佣金走 ta_guide 业务单据 + 手工/规则凭证）；purchase 仅限计调应付，不扩用其询价流 |
| 命名 | 模型 `ta.*`、视图文件 `views/*.xml`、无 Cybrosys 等第三方 fork 依赖 |
| 秘密管理 | `.env` gitignored；`TMS_FIELD_ENCRYPT_KEY` 类机制若 V20 需要加密字段，另行出方案 |

## 4. 里程碑（评审通过后启动）

| 里程碑 | 内容 | 前置 |
|--------|------|------|
| M0 | PRD-V20 + 本档评审通过；`ta_*` 命名与模块切分定稿 | 本文档 |
| M1 | ta_base + ta_route 落地，班期状态机演示 | M0 |
| M2 | ta_order + ta_finance 收款三步闭环跑通（演示线 2–3） | M1 |
| M3 | ta_dispatch + 单团核算（演示线 4–6） | M2 |
| M4 | ta_guide + 批 1 全链路验收（演示线 1–8） | M3 |
| M5 | 首批真实客户实例部署（tour.solepro.cloud 或新客） | M4 |

---

## 附：与 v19 模块清单的对照（说明收缩逻辑）

| v19（TDS-模块划分，292 人天） | V20 去向 |
|------|------|
| tour_base / tour_order / tour_operation / tour_finance / tour_commission | 重写为 ta_base / ta_order / ta_dispatch / ta_finance / ta_guide |
| tour_resource | 并入 ta_dispatch（资源条目）与 ta_route（价格体系） |
| tour_shopping / tour_approval | 批 2（ta_shopping / ta_approval） |
| tour_report | 批 2（ta_report） |
| tour_b2b / tour_api / tour_saas / tour_ai / tour_ticket | **取消**——对应永久排除 N-01..N-05 与零使用证据，PRD-V20 §4 |
