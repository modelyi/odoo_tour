# TDS-导游三层建模方案

> 文档编号：TDS-DATA-002
> 版本：v1.0
> 日期：2026-09-14
> 状态：初稿
> 维护：product-architect
> 关联：BS-09-资源管理 §3.1、TDS-DATA-001 §2.5
> 决策标签：D1=A（导游归入 hr.employee）

---

## 1. 结论

导游不再「独立于 hr.employee」建模，改为**三层分离**：

| 层 | 模型 | 职责 | 回答的问题 |
|----|------|------|-----------|
| 身份层 | `res.partner` | 自然人身份档案（姓名/身份证/联系方式/人口学信息） | 这个人是谁 |
| 劳动关系层 | `hr.employee` | 劳动关系、雇佣方式、结算打款、部门归属 | 谁在借/报/拿钱 |
| 资质薄层 | `tour.guide` | 旅游从业资质（导游证/星级/语言/服务区域） | 能不能被派团 |

- **业务调度线不动**：「能不能被派团」继续用 `tour.guide`，计调派导（BS-03）引用关系不变。
- **财务人事线统一挂 employee**：「谁在借/报/拿钱」统一挂 `hr.employee`，导游借款（`tour.guide.loan`）、报账（`tour.guide.real.pay`）、结算打款（银行卡）人事财务口径归一。
- **个税分流**：`hr.employee.employment_type` 决定税目——`service_contract`（劳务合作）→ 劳务报酬，`labor_contract`（劳动合同）→ 工资薪金。

---

## 2. 三层架构图

```
┌──────────────────────────────────────────────────────────┐
│                    导游三层建模（D1=A）                    │
│         res.partner ← hr.employee ← tour.guide           │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────┐
│      res.partner（身份层）      │   谁是谁
│  姓名 / 身份证 / 手机 / 地址 /  │   自然人身份档案
│  性别 / 民族 / 学历 / 生日…     │   （一人一份，全局唯一）
└───────────────▲──────────────┘
                │  work_contact_id（Odoo hr.employee 原生字段）
┌───────────────┴──────────────┐
│     hr.employee（劳动关系层）    │   谁在借 / 报 / 拿钱
│  employment_type（个税分流）    │   财务人事线统一挂 employee
│  工号 / 入职 / 部门 / 结算银行卡 │   雇佣关系可多条（按公司/性质）
└───────────────▲──────────────┘
                │  employee_id（tour.guide 新增 M2O）
┌───────────────┴──────────────┐
│      tour.guide（资质薄层）      │   能不能被派团
│  导游证 / 星级 / 语言 / 区域 /   │   业务调度线不动
│  领队 / 带团类型 / 司机兼导游…   │   审核状态留在资质层
└───────────────────────────────┘
```

关联链：`tour.guide.employee_id` → `hr.employee` → `work_contact_id` → `res.partner`。

---

## 3. 字段归属清单

> 依据 BS-09 §3.1 原 `tour.guide` 64 字段重新归位。`tour.guide` 从「肥模型」瘦身为「资质薄层」。

### 3.1 身份层 → `res.partner`（自然人身份）

| 字段 | 类型 | 敏感 | 说明 |
|------|------|:----:|------|
| `name` | Char | | 姓名 |
| `sex` | Selection | | 性别（男/女） |
| `nation` | Char | | 民族 |
| `born_place` | Char | | 出生地 |
| `edu` | Char | | 学历 |
| `id_num` | Char | 🔴 | 身份证号（AES-256-GCM 加密） |
| `tel` | Char | 🟡 | 固定电话（掩码） |
| `mobile` | Char | 🟡 | 手机号（掩码） |
| `zip_code` | Char | | 邮编 |
| `addr` | Char | | 通讯地址 |
| `photo` | Binary | | 照片 |
| `birthday` | Date | | 生日 |
| `marital_status` | Char | | 婚姻状况 |
| `remark` | Text | | 备注 |

### 3.2 劳动关系层 → `hr.employee`（挂 `work_contact_id`）

| 字段 | 类型 | 敏感 | 说明 |
|------|------|:----:|------|
| `work_contact_id` | M2O→res.partner | | 指向自然人身份（Odoo 原生） |
| `employment_type` | Selection | | **新增**：`labor_contract` / `service_contract`，个税分流依据 |
| `job_no` | Char | | 工号 |
| `entry_time` | Date | | 入职时间 |
| `working_date` | Date | | 工作年限起算日 |
| `career_years` | Integer | | 从业年限 |
| `department_id` | M2O→hr.department | | 所属部门（Odoo 原生） |
| `company_id` | M2O→res.company | | 所属公司（Odoo 原生） |
| `account_bank` | Char | | 开户行 |
| `account_name` | Char | | 结算账户名 |
| `account_no` | Char | 🔴 | 结算银行卡号（加密，打款载体） |
| `loan_rate` | Float | | 借款利率 |
| `cw_code` | Char | | 财务编码 |

### 3.3 资质薄层 → `tour.guide`（瘦身后保留）

| 字段 | 类型 | 敏感 | 说明 |
|------|------|:----:|------|
| `employee_id` | M2O→hr.employee | | **新增**：取代原 `partner_id` 直连身份 |
| `guide_code` | Char | | 导游证号（全局唯一） |
| `help_code` | Char | | 助记码 |
| `language_name` | Char | | 语言能力 |
| `licence` / `licence_type` | Char | | 执照（导游资格证号）/执照类型 |
| `guide_type` | Char | | 导游类型 |
| `guide_leader` / `is_tour_guide` / `is_driver_guide` | Boolean | | 是否领队 / 导游 / 司机兼导游 |
| `guide_lead_type` | Char | | 带团类型 |
| `guide_account` | Char | | 登录账号（密码走 res.users） |
| `guide_group` | Char | | 导游分组 |
| `group_type` | Char | | 团队类型偏好 |
| `shop_type` | Char | | 购物店类型偏好 |
| `guide_advantage` | Text | | 导游优势 |
| `guide_star` | Float | | 星级（0~5） |
| `grade` | Char | | 等级 |
| `recommend_class` | Char | | 推荐等级 |
| `area` / `power_area` | Char | | 服务区域 / 授权区域 |
| `driver_licence` / `driver_seat_num` / `driver_car_type` / `driver_car_name` | — | | 司机兼导游信息 |
| `active` / `audit_chk` / `audit_user` / `audit_brief` / `audit_date` | — | | 启用与审核状态 |

> `partner_id` 处理：由 `employee_id.work_contact_id` 取代，不再在 `tour.guide` 上直连身份（避免身份口径双源）。

---

## 4. 关联关系

```
业务调度线（不动）：
    tour.plan（派导安排，BS-03）──▶ tour.guide.employee_id ──▶ hr.employee ──▶ res.partner

财务人事线（统一挂 employee）：
    tour.guide.loan（导游借款）   ──▶ hr.employee（谁在借）
    tour.guide.real.pay（导游报账）──▶ hr.employee（谁在报）
    结算打款（account_no）         ──▶ hr.employee（谁在拿钱）

身份基线：
    hr.employee.work_contact_id ──▶ res.partner（自然人身份，一人一份）
```

- `tour.guide` : `hr.employee` = N:1（一名导游对应一条雇佣关系；同一自然人若在多家公司有资质，可多 `tour.guide` 指向多条 `hr.employee`）。
- `hr.employee` : `res.partner` = N:1（`work_contact_id`，一个自然人身份可挂多条雇佣关系记录）。

---

## 5. 个税分流（employment_type）

| `employment_type` | 适用情形 | 税目 | 计税方式 |
|-------------------|----------|------|----------|
| `labor_contract` | 劳动合同制导游 | 工资薪金所得 | 综合所得 3%~45% 七级超额累进（累计预扣法） |
| `service_contract` | 劳务合作制导游 | 劳务报酬所得 | 预扣率三级：≤2 万 20%、2~5 万 30%（速算扣除 2000）、>5 万 40%（速算扣除 7000） |

> 劳务报酬费用减除：每次收入 ≤4000 元减 800 元、>4000 元减 20%，再按三级超额累进预扣。`employment_type` 决定申报表与预扣税率，字段定义在 `hr.employee`，由个税申报岗读取（配合 FINANCE-COMPLIANCE-BASELINE 的敏感字段授权）。

---

## 6. 迁移方案（分阶段、非破坏）

| 阶段 | 动作 | 是否破坏现有 |
|------|------|:------------:|
| 0 现状 | `tour.guide` 肥模型（64 字段）直连 `partner_id`；`hr.employee` 仅承载 org users；无 `employment_type` | — |
| 1 增列 | `hr.employee` 新增 `employment_type` Selection；`tour.guide` 新增 `employee_id` M2O | 否（加字段） |
| 2 建关系 | 为 2173 名导游批量建 `hr.employee`（`work_contact_id`→导游 partner），回填 `tour.guide.employee_id`；幂等脚本 + 校验身份证/银行卡密文迁移口径 | 否（回填引用） |
| 3 劳动关系字段迁移 | 工号/入职/部门/结算银行卡/借款利率/财务编码 从 `tour.guide` 迁至 `hr.employee`（先 related 读，稳定后删列） | 是（字段搬家，需回归） |
| 4 身份字段去重 | 身份字段（姓名/身份证/手机…）从 `tour.guide` 改由 `employee_id.work_contact_id` 读取，物理迁移至 `res.partner` | 是（字段搬家） |
| 5 财务人事线切换 | 借款/报账的收款人口径从 `tour.guide` 切到 `hr.employee`（单据仍保留 `guide_id` 外键，经 `guide.employee_id` 关联，不破坏现有单据） | 渐进 |
| 6 个税分流上线 | 按 `hr.employee.employment_type` 分流申报税目与预扣税率 | 否（新增逻辑） |

**迁移原则**：全程幂等可重跑；敏感字段（`id_num`/`account_no`）沿用 `tour.encrypted.field.mixin` 加密口径，杜绝明文中间态；每阶段灰度 + 单团回归。

---

## 7. 风险与应对

| # | 风险 | 应对 |
|---|------|------|
| 1 | 现有外键耦合：`tour.guide.loan` / `tour.guide.real.pay` / `tour.shop.record` 等大量 `guide_id → tour.guide` | 单据仍挂 `guide_id`，经 `guide.employee_id` 关联到 employee，不做破坏性外键迁移 |
| 2 | `hr.employee` 语义重：Odoo 原生合同/考勤/工资（hr_contract、hr_payroll）若启用需评估冲突 | `employment_type` 为自定义字段，与 hr_contract 解耦；一期不引入 payroll |
| 3 | 一人多角色/多公司：同一自然人可能多份雇佣关系 | `res.partner` 唯一自然人，`hr.employee` 按雇佣关系可多条；`tour.guide` 按资质可多条 |
| 4 | 数据迁移成本：2173 条建 employee + 字段回填 | 幂等脚本 + 迁移后对账（身份/银行卡/部门一致性校验） |
| 5 | 敏感字段双处存留：迁移期 `id_num`/`account_no` 在 guide 与 partner/employee 双处 | 统一 `tour.encrypted.field.mixin`，切换期以单一真相源为准，审计日志留痕 |
| 6 | 派团线回归：瘦身误删资质字段破坏派导/检索 | 资质字段一律留 `tour.guide`；改动前后跑 UAT 派导场景 |

---

## 8. 影响与后续

- **BS-09 §3.1**：设计决策由「不用 hr.employee」改为「导游归入 hr.employee（D1=A）」，字段表按本方案三层归位（见 BS-09 回改）。
- **TDS-DATA-001 §2.5**：`tour.guide` 字段表需按本方案瘦身并新增 `employee_id`、`employment_type`（后续同步）。
- **BS-05/06/15 财务线**：借款/报账/打款的「人」统一走 `hr.employee`，与 BS-15 全员自助合规口径对齐。
- **合规基线**：`employment_type` 作为个税分流的判定字段，纳入个税申报与敏感字段授权（FINANCE-COMPLIANCE-BASELINE）。
