# TDS-财务记账对接

> 文档编号：TDS-FIN-001
> 版本：v1.0
> 日期：2026-09-13
> 状态：初稿
> 依据：SOUL（产品架构师）、BS-05 财务管理 v2.0、BS-07 往来对账、现有 tour_finance 6 模型源码、Odoo 19 account/analytic 源码

---

## 一、背景与目标

用户定调：**财务用 Odoo 原生 account 逻辑**。tour_finance 从「自研金额字段」重构为「account 的薄业务层」。

核心原则（对齐 SOUL「简单优先」）：

1. **记账事实来源 = account.move / account.move.line**，不再由 tour.* 自研 Float 字段充当账本。
2. tour_finance 只保留 account 无法表达的业务语义（差额征税成本分类、发票缺口、对账职务分离、收款认领状态机、佣金个税计算）。
3. **单团核算 = analytic**，不做自研收入/成本/利润字段。
4. 每个自研模型要么**废弃并迁移到 account 原生对象**，要么**保留但金额字段改由 account 派生**。

---

## 二、模块依赖

### 2.1 决策

| 模块 | 是否硬依赖 | 理由 |
|------|-----------|------|
| `account` | ✅ **必加** | 凭证/对账/账户的事实来源 |
| `analytic` | ✅ **必加** | 单团核算（analytic_distribution + account.analytic.account） |
| `l10n_cn` | ❌ 不硬依赖 | 见 2.2 |

### 2.2 l10n_cn 决策（不写入 depends）

`l10n_cn` 本质是「中国准则科目表 + 增值税税种」的**数据模块**，不是逻辑模块：

- **好处**：开箱即得中国会计科目（1002 银行存款、1122 应收账款、2203 预收账款、6001 主营业务收入、6401 主营业务成本等）和增值税税种模板。
- **风险**：硬依赖会强制安装一份可能不合用的科目表，且旅行社「差额征税（6%，财税2016-36号）」需要自建税种/税目，l10n_cn 不能直接覆盖。
- **现实**：当前 addons 目录**未包含 l10n_cn**，且已有 `base_accounting_kit`（Cybrosys，依赖 account+analytic+base_account_budget）提供中国式报表。

**结论**：

- `depends` 只写 `account`、`analytic`（+ 现有 `base, mail, tour_base, tour_resource, tour_order`）。
- 在**部署要求**中标注：生产环境必须安装一套中国科目表（推荐 `l10n_cn`，或提供 tour_finance 自带科目模板数据文件 `data/chart_template_*.xml` 作为兜底）。
- tour_finance 提供「资金科目/预收/佣金/个税」等**科目编码的配置化映射**（见 §五），不写死科目 id，以兼容不同科目表。

### 2.3 最终 manifest depends

```python
'depends': [
    'base', 'mail',
    'account', 'analytic',          # 新增
    'tour_base', 'tour_resource', 'tour_order',
],
```

> 注意：`tour_shopping` 当前依赖 `tour_finance`，佣金模型 `tour.commission` 位于 tour_finance（并非蓝图 TDS-MOD 中规划的独立 `tour_commission` 模块）。本方案沿用现状，不在本次调整模块归属。

---

## 三、总体架构

```
┌────────────────────────────────────────────────────────────┐
│                  account 原生层（事实来源）                  │
│  account.journal        account.move        account.move.line│
│  account.account        account.analytic.account             │
│  account.analytic.line  (reconcile / partial reconcile)     │
└───────────────────────────────┬────────────────────────────┘
                                │ 薄业务层：触发凭证 + 保留业务语义
┌───────────────────────────────▼────────────────────────────┐
│                      tour_finance 业务层                    │
│  tour.payment.claim  收款认领（状态机 → 生成收款凭证）        │
│  tour.plan.account   单团核算（绑定 analytic，差额征税语义）  │
│  tour.reconciliation 业务对账（11类，金额由 move.line 派生）  │
│  tour.commission     佣金个税（发放 → 生成付款/代扣凭证）     │
│  tour.pay.channel    支付渠道（映射到 journal + 资金科目）    │
└────────────────────────────────────────────────────────────┘
```

**关键不变量**：

- 任何影响资金/往来/收入/成本的业务动作，最终都要落到一张 `account.move`。
- 凭证行（account.move.line）的金额字段是唯一记账真相；tour.* 的金额字段只做「展示缓存 / 派生计算 / 业务规则校验」。
- 单团核算靠 `analytic_distribution` 挂在每一行凭证上，由 `account.analytic.line` 汇总成团利润。

---

## 四、各模型处置（逐个）

### 4.1 tour.bank.account — 🔴 废弃（迁移）

| 现有字段 | 迁移去向 |
|---------|---------|
| name | account.journal.name |
| bank_id (res.bank) | account.journal.bank_id（Odoo 19 journal 有 bank_id） |
| acc_number（敏感） | res.partner.bank.acc_number（journal.bank_account_id） |
| acc_number_masked | res.partner.bank 扩展 `tour_acc_number_masked`（掩码 computed） |
| currency_id | account.journal.currency_id |
| account_type (bank/cash/third_party) | account.journal.type：bank→`bank`、cash→`cash`、third_party→`bank`（挂第三方资金科目 1012） |
| balance | ❌ 废弃（余额由 account.move.line 对账派生，见 journal 的 bank statement） |
| taxpayer_no / power_area / remark | account.journal 扩展字段 `tour_*`（或 res.partner 上） |
| trans_fee_rate | tour.pay.channel 或收款单上（原就有，见 4.4） |
| company_id / department_id | account.journal.company_id（journal 无 department，department 由凭证行 analytic 或扩展承载） |

**决策**：**废弃** `tour.bank.account`，改用 **account.journal（bank/cash）** + 卡号挂 **res.partner.bank**。理由：

- 收款/付款必须落到 journal，账户余额、银行对账单（bank statement）、银行对账都在 account 侧，自建账户模型必然双份数据。
- 卡号加密（原 TODO）迁移到 `res.partner.bank` 扩展字段，Odoo 原生 bank 记录已有掩码展示惯例。
- 迁移脚本：72 条 tour.bank.account → 每账户生成 1 个 journal + 1 条 res.partner.bank，journal.bank_account_id 指过去。

### 4.2 tour.pay.channel — 🟢 保留（改造）

| 现有字段 | 处置 |
|---------|------|
| name / channel_type / sequence / active | 保留 |
| fund_account_code（裸编码字符串） | 🔴 改为 `fund_account_id` Many2one('account.account')，按 `code_store` 反查 |
| fund_account_name | ❌ 删除（账户名由 account.account.name 派生） |
| company_id | 保留 |

**决策**：保留为「资金通道配置表」，但把裸编码 `fund_account_code` 升级为 `fund_account_id`（指向 account.account）。渠道 → journal 的映射关系：

| channel_type | 默认 journal.type | 资金科目（fund_account_id 默认值） |
|-------------|------------------|----------------------------------|
| bank_transfer | bank | 1002 银行存款 |
| wechat | bank（第三方） | 1012 其他货币资金 |
| alipay | bank（第三方） | 1012 其他货币资金 |
| cash | cash | 1001 库存现金 |
| other | general | 由用户指定 |

**改造**：为每个 channel 增加 `journal_id` Many2one('account.journal')，收款时从 channel 取 journal + 资金科目，实现「渠道 → journal → 凭证」自动路由。

### 4.3 tour.plan.account — 🟢 保留（改造为 analytic 包装）

| 现有字段 | 处置 |
|---------|------|
| plan_id / plan_code / biz_mode | 保留 |
| analytic_account_id | ✅ **升级为主键**：required、ondelete='restrict'，自动创建 |
| income_total / cost_total / profit / profit_no_shop | 🔴 废弃 compute ← plan.*，改由 analytic 派生（account.analytic.line 汇总） |
| income_commission | 保留（购物佣金收入，经营收入语义，analytic 无） |
| cost_deductible / cost_non_deductible | 保留（差额征税成本分类，account 无此语义） |
| receivable / prepaid | 🔴 改为由 account.move.line（该 plan 的 analytic 下未核销应收/预收）派生 |
| invoice_gap | 保留（发票缺口，业务语义） |
| state | 保留（核算中/已结算/已归档，驱动 analytic account 的 active/归档） |

**决策**：`tour.plan.account` 退化为 **analytic 账户的业务别名层**。

- **analytic account 是单团核算的事实来源**，收入/成本/利润从 account.analytic.line 汇总。
- tour.plan.account 只保留 analytic 无法表达的字段（差额征税成本分类、购物佣金收入、发票缺口、状态）。
- 创建时机：`tour.plan` 确认（confirmed）或首个收款/成本发生时，自动创建 tour.plan.account + account.analytic.account（一对一）。

### 4.4 tour.payment.claim — 🟢 保留（改造，核心）

| 现有字段 | 处置 |
|---------|------|
| name / payee_id / supplier_id / pay_date / pay_money / brief / star_state | 保留 |
| use_money / balance_money | 🔴 改为由 account.move.line 派生（该收款凭证的已核销余额） |
| account_id (→ tour.bank.account) | 🔴 改为 `journal_id` Many2one('account.journal') |
| plan_id / plan_code | 保留（认领到团） |
| pay_way_id / pay_channel_id | 保留（决定凭证的资金科目 + journal） |
| bank_name_pay / account_name_pay / account_no_pay / tax_code | 保留（付款方信息，展示用） |
| trans_fee_rate / trans_fee | 保留（决定手续费分录） |
| claim_state | 保留（状态机，见 §5.2） |
| — 新增 | `move_id` Many2one('account.move')，`move_state` related |

**决策**：保留认领状态机 + 业务字段，金额侧新增 `move_id` 关联收款凭证，`balance_money` 改为派生。

### 4.5 tour.reconciliation — 🟢 保留（改造）

| 现有字段 | 处置 |
|---------|------|
| name / verify_type / supplier_id / period / state / 职务分离校验 | 保留（业务对账语义） |
| total_amount / settled_amount / unsettled_amount | 🔴 改为由 account.move.line（该 supplier 的 open 项）派生 |
| invoice_collected / invoice_gap | 保留（发票归集，业务语义） |
| aging_days | 保留（账龄，可从 move.line date_maturity 派生） |
| line_ids（明细行） | 保留，金额派生 + 新增 move_line_ids 关联 |

**决策**：**保留** tour.reconciliation 作为「业务对账台账」（11 类，含发票合规、账龄、职务分离），**同时**引入 account 原生核销：

- 「财务核销」（这笔钱和那笔账对平）→ `account.move.line` 的 reconcile（partial/full），Odoo 原生对账引擎 + `account.reconcile.model`。
- 「业务对账」（这个团和这个地接社往来是否清晰、发票是否合规）→ tour.reconciliation。
- 明细行金额由「该 plan（analytic）+ 该 supplier 的未核销 move.line」派生，确认时触发批量核销。

### 4.6 tour.commission — 🟢 保留（改造）

| 现有字段 | 处置 |
|---------|------|
| 佣金来源（plan_id / shop_id / agreement_id / commission_rate / shop_amount / commission_total） | 保留 |
| 导游分成（guide_id / guide_share_rate / guide_share_before_tax / premium） | 保留 |
| 个税（guide_tax_type / guide_tax / guide_net_pay / company_retain） | 保留（个税计算逻辑不变） |
| state / confirm_uid / confirm_date | 保留，新增动作生成凭证 |
| — 新增 | `move_id`（计提凭证）、`pay_move_id`（发放凭证） |

**决策**：保留佣金个税计算，确认/发放时生成 account.move（见 §5.6）。

---

## 五、技术实现路径

### 5.1 银行账户 / 资金科目

- 每个 `tour.pay.channel` 绑定 `journal_id` + `fund_account_id`。
- 收款凭证：`journal_id = channel.journal_id`，资金行 `account_id = channel.fund_account_id`。
- 提供 `res.config.settings` 配置项：默认预收科目、佣金费用科目、代扣个税科目、手续费科目、主营收入/成本科目（差额征税用）。

### 5.2 收款（tour.payment.claim → account.move）

**认领状态机与凭证联动**：

```
待认领(0) ──action_claim──▶ 待审核(1) ──action_audit──▶ 已审核(2) ──action_settle──▶ 已平账(3)
                  ▲                                              │
                  └──────────────action_reject────────────────────┘
```

| 状态流转 | 会计动作 |
|---------|---------|
| 0 → 1 认领 | 无（仅挂 plan_id + 校验资金账户） |
| 1 → 2 审核 | **生成收款凭证** account.move（draft → 直接 action_post），claim.move_id 记录 |
| 2 → 3 平账 | **预收 → 收入确认**（可选，见 5.3 收入确认阶段），或仅标记核销 |
| 1 → 0 退回 | 若已生成凭证则 `button_draft` → 作废/删除 |

**收款凭证分录**（审核时生成）：

```
借：银行存款 / 其他货币资金   (channel.fund_account_id)   pay_money
    贷：预收账款-客户           (预收科目，partner=supplier)  pay_money
[若 trans_fee > 0]
    借：财务费用-手续费         (手续费科目)                trans_fee
    贷：银行存款               (channel.fund_account_id)   trans_fee
```

每行挂 `analytic_distribution = {str(plan.analytic_account_id): 100.0}`。

**为什么不走 account.payment**：account.payment 用于「支付供应商 / 收自客户」并匹配账单（invoice/bill）。本场景是「先收后认领」的裸收款，没有 account.move 账单可匹配，直接生成 `move_type='entry'` 的收款凭证更简洁、更符合「薄业务层」定位。

### 5.3 单团核算（analytic）

1. `tour.plan` 进入 `confirmed` 时，自动创建 `tour.plan.account`，并连带创建 `account.analytic.account`：
   - `name = f'{plan.plan_code} {plan.plan_name}'`
   - 通过 `_inherit = 'account.analytic.account'` 增加 `tour_plan_id`（Many2one tour.plan）反向关联。
2. 所有涉及该团的收入/成本凭证行，`analytic_distribution` 强制写入 `{str(analytic_account_id): 100.0}`。
3. 团利润 = `account.analytic.line` 按 analytic_account_id 汇总（credit - debit 或按 account 方向），tour.plan.account 的 income_total/cost_total/profit 改为 `compute` 从 analytic.line 读取（或提供报表向导，不落库）。

**收入确认阶段（差额征税，后续深化）**：平账/出团完成时生成收入凭证：

```
借：预收账款           (团款已收部分)
    贷：主营业务收入     (差额口径收入)
    贷：应交税费-应交增值税(销项，6% 差额计征)
借：主营业务成本       (可扣除成本 cost_deductible)
    贷：应付账款-供应商
```

> 增值税差额征税（财税2016-36号）涉及税目、可扣除成本清单、纳税申报表，作为 **Phase 2** 单独设计，本方案只预留科目配置 + cost_deductible/cost_non_deductible 字段位。

### 5.4 对账（reconcile + tour.reconciliation）

- **往来核销**：收款凭证的「预收」行与后续「收入/应收」行通过 `account.move.line` 的 reconcile 核销；供应商付款同理。提供 `account.reconcile.model` 预设（按 partner + analytic 自动匹配）。
- **业务对账**：tour.reconciliation 明细行金额 = 该 supplier 在该 plan（analytic）下的 open move.line 汇总。`action_verify` 只读核对；`action_settle` 触发 `move_line_ids` 的批量 `reconcile()`。

### 5.5 佣金/个税（tour.commission → account.move）

**确认（action_confirm）** 生成计提凭证：

```
借：销售费用-佣金       (佣金费用科目)           guide_share_before_tax + premium
    贷：其他应付款-导游  (其他应付，partner=guide) guide_net_pay
    贷：应交税费-代扣个人所得税                   guide_tax
```

**发放（新增 action_pay）** 生成付款凭证：

```
借：其他应付款-导游   guide_net_pay
    贷：银行存款        guide_net_pay
[代缴时]
借：应交税费-代扣个人所得税  guide_tax
    贷：银行存款              guide_tax
```

> 佣金总额 commission_total 是「购物店返佣经营收入」，其收款走 5.2 收款流程（可自动/手动生成一张佣金收款单）。公司留存 = commission_total - 税前分成 - 奖金，是收入减费用后的利润，不需单独分录。

---

## 六、凭证生成代码思路

### 6.1 通用 helper（tour_finance 内混入类）

```python
# models/accounting_mixin.py
class TourAccountingMixin(models.AbstractModel):
    _name = 'tour.accounting.mixin'

    def _get_company_currency(self):
        return self.env.company.currency_id

    def _plan_analytic_distribution(self, plan):
        """返回单团 analytic_distribution dict，plan 无 analytic 时返回空。"""
        aa = plan.analytic_account_id
        return {str(aa.id): 100.0} if aa else {}

    def _make_move(self, journal, date, ref, lines, move_type='entry'):
        """lines: list[dict(account_id, partner_id, debit, credit, analytic, name)]"""
        move_vals = {
            'move_type': move_type,
            'journal_id': journal.id,
            'date': date,
            'ref': ref,
            'line_ids': [],
        }
        for ln in lines:
            move_vals['line_ids'].append((0, 0, {
                'account_id': ln['account_id'],
                'partner_id': ln.get('partner_id'),
                'debit': ln.get('debit', 0.0),
                'credit': ln.get('credit', 0.0),
                'analytic_distribution': ln.get('analytic'),
                'name': ln.get('name', ref),
            }))
        return self.env['account.move'].create(move_vals)
```

### 6.2 收款凭证（claim.action_audit 内）

```python
def _generate_receipt_move(self):
    self.ensure_one()
    channel = self.pay_channel_id
    journal = self.journal_id or channel.journal_id
    fund_acc = channel.fund_account_id
    prepay_acc = self.env['ir.config_parameter']  # 或 res.config.settings 读取
    analytic = self._plan_analytic_distribution(self.plan_id)

    lines = [{
        'account_id': fund_acc.id,
        'partner_id': self.supplier_id.id,
        'debit': self.pay_money,
        'analytic': analytic,
        'name': f'收款认领 {self.name}',
    }, {
        'account_id': prepay_acc.id,   # 预收账款
        'partner_id': self.supplier_id.id,
        'credit': self.pay_money,
        'analytic': analytic,
        'name': f'收款认领 {self.name}',
    }]
    if self.trans_fee > 0:
        lines.append({
            'account_id': fee_acc.id,       # 财务费用-手续费
            'debit': self.trans_fee,
            'analytic': analytic,
        })
        lines.append({
            'account_id': fund_acc.id,
            'credit': self.trans_fee,
            'analytic': analytic,
        })

    move = self._make_move(journal, self.pay_date, self.name, lines)
    move.action_post()
    self.move_id = move.id
```

### 6.3 单团 analytic 账户创建（tour.plan.account.create）

```python
@api.model_create_multi
def create(self, vals_list):
    res = super().create(vals_list)
    for rec in res:
        if not rec.analytic_account_id:
            rec.analytic_account_id = self.env['account.analytic.account'].create({
                'name': f'{rec.plan_code} {rec.plan_id.plan_name}',
                'tour_plan_id': rec.plan_id.id,
                'company_id': rec.company_id.id,
            }).id
    return res
```

> 需在 `_inherit = 'account.analytic.account'` 中新增 `tour_plan_id = fields.Many2one('tour.plan', ...)`，并加 `models.Constraint('unique(tour_plan_id)')` 保证一团一核算。

### 6.4 佣金计提/发放（tour.commission）

```python
def action_confirm(self):
    for rec in self:
        # ... 原状态校验 ...
        rec.write({'state': 'confirmed', ...})
        rec.move_id = rec._generate_commission_move()  # 计提凭证（分录见 5.5）

def action_pay(self):
    for rec in self:
        if rec.state != 'confirmed':
            continue
        rec.pay_move_id = rec._generate_payment_move()  # 发放凭证
        rec.state = 'paid'
```

---

## 七、Odoo 19 API 注意事项

### 7.1 account.account 的 code → code_store

- Odoo 19 中 `account.account.code` 是 **compute 字段**（`_compute_code` / `_inverse_code` / `_search_code`），实际存储靠 `code_store`（`company_dependent=True`）。
- **不要**直接传 `company_id`（Odoo 19 已移除该字段）；账户通过 `company_ids`（Many2many）多公司共享，公司上下文由环境决定。
- 查找账户用 `self.env['account.account'].search([('code_store', '=', '1002')])`（或 `('code', '=', '1002')`，search 方法已映射到 code_store），**不要**写死 account id。
- XML/demo 数据里 `<record model="account.account">` 不能再写 `company_id`。

### 7.2 analytic_distribution 字段

- `account.move.line.analytic_distribution` 是 JSON dict：`{str(analytic_account_id): percentage}`。
- 百分比按「分析计划（analytic.plan）」分组求和，本方案只用单计划，恒为 `{id: 100.0}`。
- 凭证 `action_post()` 后自动生成 `account.analytic.line`。

### 7.3 account.move 创建

- `account.move.create` 需 `journal_id` + `date` + `ref` + 至少两条 line 且借贷平衡。
- line 用 `(0, 0, {...})` 命令创建，字段填 `account_id`（id，非 code）、`partner_id`、`debit`/`credit`、`analytic_distribution`、`name`。
- 生成后用 `move.action_post()` 过账；退回用 `move.button_draft()` → `unlink()` 或 `_reverse_moves()`。
- 多币种场景用 `amount_currency`，本方案默认单币种（人民币），`currency_id` 走公司币。

### 7.4 models.Constraint（已用）

- Odoo 19 将 `_sql_constraints` 列表改为命名类属性 `models.Constraint('unique(...)', '提示')`，现有 tour_finance 代码已采用，新增约束沿用此写法（如 analytic 账户的 `unique(tour_plan_id)`）。

### 7.5 其他

- `account.analytic.account` 扩展需在 tour_finance 里 `_inherit`，注意 `plan_id` 字段名与 `account.analytic.account.plan_id`（指向 account.analytic.plan）冲突，新增反向字段必须用新名（如 `tour_plan_id`）。
- 对账核销：Odoo 19 `button_draft()` 不再自动 `remove_move_reconcile()`，自定义逆向流程需显式调用。

---

## 八、迁移方案与工作量

### 8.1 迁移脚本清单

| 迁移项 | 内容 |
|-------|------|
| M1 银行账户 | 72 条 tour.bank.account → account.journal + res.partner.bank（含卡号掩码字段迁移） |
| M2 支付渠道 | fund_account_code 裸编码 → fund_account_id（按 code_store 反查），补 journal_id |
| M3 单团核算 | 存量 tour.plan → 批量创建 account.analytic.account + tour.plan.account（或按需懒创建） |
| M4 收款认领 | 存量 claim → 补齐 journal_id，历史收款选择性补记凭证（或仅新单生效） |
| M5 对账/佣金 | 金额字段切到 move.line 派生（历史数据可保留原字段值作为快照） |

### 8.2 工作量预估

| 任务 | 人天 |
|------|------|
| 模块依赖 + 科目/渠道/预收等配置模型 | 3 |
| 银行账户废弃 + journal 迁移 | 4 |
| 收款凭证生成 + 状态机联动 | 5 |
| 单团核算 analytic 改造 | 4 |
| 对账 reconcile 联动 | 4 |
| 佣金个税凭证 | 3 |
| 迁移脚本 | 4 |
| 单元测试 | 5 |
| **合计** | **32 人天** |

---

## 九、风险与待决

| # | 风险/待决 | 说明 | 建议 |
|---|----------|------|------|
| 1 | 科目表来源 | l10n_cn 未安装，科目编码不定 | 部署时安装 l10n_cn 或提供 tour_finance 自带科目模板；科目走配置不写死 |
| 2 | 差额征税（增值税 6%） | 收入确认涉及税目/申报，复杂度高 | 明确划入 Phase 2，本方案只留字段位 + 科目配置 |
| 3 | 历史收款是否补记凭证 | 存量 51+ 收款若补记会影响报表 | 建议新单生效 + 历史数据保留快照，不强制回补 |
| 4 | tour_shopping 依赖 tour_finance | 佣金模型在 tour_finance，shopping 反向依赖 | 本次不改；如需独立 tour_commission 模块另立项 |
| 5 | account.analytic.account 反向字段命名 | plan_id 已被占用 | 统一用 `tour_plan_id`，避免字段名冲突 |

---

## 附：字段/对象映射速查

| 易途/自研 | Odoo 19 原生 |
|----------|-------------|
| 银行账户 | account.journal（type=bank/cash）+ res.partner.bank |
| 资金科目编码 | account.account（code_store 反查） |
| 收款凭证 | account.move（move_type='entry'） |
| 收款认领余额 | account.move.line 未核销余额 |
| 单团核算 | account.analytic.account + account.move.line.analytic_distribution |
| 团利润 | account.analytic.line 汇总 |
| 往来核销 | account.move.line.reconcile() |
| 佣金计提/发放 | account.move（费用/应付/个税分录） |
