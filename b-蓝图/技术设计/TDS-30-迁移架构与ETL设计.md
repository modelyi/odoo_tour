# TDS-30 迁移架构与 ETL 设计（TMS 19 → tour 20）

- 版本：v0.1（Phase B0 产出，2026-09-21）
- 上游计划：`b-蓝图/技术设计/迁移与升级计划-TMS到tour.md` §6（B0）/ §7（B1）/ §8（B2）
- 目的：把 B0 可行性 spike 的**实测证据**固化成结论，据此冻结 B1 的范围与工作量。
- 本文所有数字均可用 §7 的命令复现；不含任何业务数据行、密钥或连接串。

---

## 1. B0 方法（怎么测的）

| 步骤 | 做法 | 产物 |
|---|---|---|
| 1 | 19 侧列快照：现网库 `tms` 的 `information_schema.columns` | 10,008 列 |
| 2 | 19 侧字段归属：`ir_model_fields` × `ir_model_data` 把每列映射到**声明它的模块** | 15,403 条 (表,列)→模块 |
| 3 | 20 侧参考库：`b0snap20` 空库装 tour_* 的**官方依赖闭包**（102 模块，含 account/hr/fleet/website_sale 等） | 6,288 列 |
| 4 | 两侧 join 出「19 有 20 无」「类型变化」「20 新增」，并用 `count(*) filter (where …)` 抽样（每表 ≤5 万行）测出**删除列的填充率** | 见 §4 |
| 5 | 模型级 diff：`ir_model` 两侧对比，只保留「20 里同名模块已装却没有该模型」的严格候选 | 22 个（§3） |
| 6 | 第三方模块逐个试装到 20：`-i <模块>` 一条命令一个模块，记录首个失败原因 | 37 行判定表（§5） |

> 说明：试装前必须先把 manifest 的 `version` 改成 `20.1.x`（原因见 §3-F1），改写只落在
> `/tmp/b0/tp20addons` 副本里，**没有动仓库源码**。

## 2. 模块总量（187 已装）

| 分类 | 数量 | 20 侧结论 |
|---|---|---|
| 官方模块，20 社区版仍在 | **140** | 无需改码；装完即用，数据靠 B2 的 ETL |
| 官方模块，20 社区版已删除 | **11** | 逐个决策（§6） |
| 自研 `tour_*` | **21** | 全部需适配（§5） |
| Webkul OHRMS | **14** | 全部需适配（§5） |
| OCA `web_responsive` | **1** | 20 试装**直接通过** |
| `tour_tutor`（在 addons 里但未安装） | 1 | 与本次迁移无关，建议归档 |

## 3. 七条决定性硬事实（B1 的范围由此定形）

- **F1 版本门禁**：Odoo 20 `odoo/modules/module.py:500` 新增 `check_version()`，要求
  `major_version = '20.1'`，即模块 `version` 必须以 **`20.1.`** 开头，且
  `adapt_version()` 只接受 **2–5 段**版本号。不满足 → `installable=False`，模块**连出现在安装列表里都不可能**。
  → 36 个第三方模块（含 21 个 tour_*）的 manifest 必须批量改版本号；AGENTS.md 的
  版本约定要同步改成 `20.1.0.x.0`。
- **F2 权限模型重写**：20 社区版**删除了 `ir.model.access` 与 `ir.rule` 两张表**
  （`b0snap20` 的 `information_schema.tables` 里查不到），统一成
  `odoo/addons/base/models/ir_access.py` 的 **`ir.access`**：
  `operation ∈ {c,r,u,d}` + `domain`（记录规则）+ `kind ∈ {permission, restriction}`。
  **注意 `operation` 是 Selection 而非任意子串**：合法值只有 `ir_access.py:16 CRUD_SELECTION`
  的 15 个键，键内顺序固定为 `crud` —— `rud` 合法、`rucd`/`ruc`/`rc`/`ucd` 不合法，
  非法值被写成 NULL 后撞 `not-null` 约束**整批装载失败**。权限转换工具 v3 就因此
  有 **959/1,524 行**在真实 registry 上装不进去（见下）。
  → 这是 B1 **最大的单一工作量**：36 个模块共 ~300 行 `security/*.csv` + 91 条
  `model="ir.rule"` 的 XML 要重写；现网数据侧有 **516 行 ir_model_access + 198 行 ir_rule**
  （挂在 tour_* 模型上）要在 ETL 象限 3 里转换成 `ir.access` 行。
  首失败样本：`KeyError: 'ir.model.access'`（hr_custody 等）、
  `ParseError … security/hr_reminder_security.xml`、`ParseError … tour_budget/security/account_budget_security.xml`。
  → **该重写已被工具化并在真实 20 registry 上验证**（`c-系统实现/tms-platform/scripts/migration/security_19to20/`）：
  19 现网 1,405 access + 431 rule → 按人群重建出 **1,407 permission + 117 restriction** 行、
  待人工复核 14 项；抽样 188 行装进 scratch 库 `b1sec7` **0 ERROR**，
  行为探针确认带 `domain` 的行在查询期真的收窄（portal 用户 `tour.guide` 2 可见 1、
  域外 `read()` 报 `AccessError`、superuser 对照可见 2）。
  **结论：转换层不能只靠读 CSV 自审，必须过一次真实装载** —— 上面那个 959 行的缺陷
  在文本层面完全看不出来。
- **F3 `res.bank` 模型整体删除**：20 侧 `grep -r "_name = 'res.bank'"` 无结果，
  银行信息被**扁平化进 `res_partner_bank`**（新增列 `bank_name/bank_bic/city/street/street2/zip/state_id/country_id/clearing_label_id`）。
  同时 `acc_number→account_number`、`acc_holder_name→holder_name`、
  `sanitized_acc_number→sanitized_account_number`，且 **`currency_id` 在新表里没有了**。
  → 自研模型 `tour.bank.account`（在 `tour_base`）以 `res.bank` 为 comodel，registry 加载期
  `AssertionError: Field tour.bank.account.bank_id with unknown comodel_name 'res.bank'`，
  **连锁阻塞 19 个 tour_*** 模块（它们都依赖 tour_base）。
  → 迁移风险叠加：`res_partner_bank.acc_number` 是 A0-2 认定的**密文列**，改列名 + 改模型 = 必须在
  ETL 里显式解密/重加密路径，并且要先确认 `TMS_FIELD_ENCRYPT_KEY` 一致。
- **F4 `odoo.service.db` 整体消失**：20 只剩 `common/model/server`，
  `tour_saas` 加载期 `ModuleNotFoundError: No module named 'odoo.service.db'`（5 处引用）。
  → 维持计划 §7 的决定：**tour_saas 本期停用**，多租户 SaaS 化正式移出范围。
- **F5 `hr.leave.type` 模型消失**：20 全树 0 引用，`hr_holidays` 重构后只剩
  `hr.leave` / `hr.leave.allocation` / `hr.leave.accrual.*` / `hr.leave.mandatory.day` 等。
  → Webkul 的 4 个模块（hr_payroll_community、hr_payroll_account_community、ohrms_loan*、
  ohrms_salary_advance）报 `TypeError: Model 'hr.leave.type' does not exist in registry`。
  **在假勤重构映射确定前，这 7 个 OHRMS 模块无法评估工作量。**
- **F6 前端与报表**：`publicWidget` 注册表已移除 → `tour_website_sale/tour_website_sale.js`
  （3 处）必须 OWL 重写；`tour_accounting` 的 6 个 JS 已是 `@odoo-module`，可平移。
  20 社区版 `account/report/` 仍**没有**总账/余额表 → 报表层必须保留（计划 §7 判定成立）。
- **F7 `res.users` 的组字段改名**：19 的 `groups_id` → 20 的 **`group_ids`**
  （`odoo/addons/base/models/res_users.py:251`，关系表仍是 `res_groups_users_rel(uid,gid)`，
  所以象限 3 的直拷 SQL 不受影响），并新增 `all_group_ids`（**传递闭包**后的组集）与
  `base.group_user_regular` 这个新基线组。所有 `env['res.users'] … groups_id` 的读写、
  以及验收脚本里的用户-组断言都要改名，且"该用户属于哪些组"的判定应改用 `all_group_ids`。
  `res.groups.implied_ids` 的关系表和 gid/hid 方向在 20 **未变**（`res_groups.py:75`）
  → 权限重建脚本按继承链算人群的逻辑在两侧通用。
  另：CLI 层 `--without-demo=all` 自 19 起是**非法布尔值**（WARNING 后退化成 True），
  B2 的 ETL/装载命令串要去掉 `=all`。

## 4. 字段级 diff（数据丢失风险清单）

- 两侧共有表 **554** 张；「19 有 / 20 无」的列 **542**，其中归属到 20 已装模块的
  **154 列**为真实删除；其余 388 列属于 20 未装模块或自定义模块，不是问题。
- 对 154 列做了填充率抽样：**只有 51 列在生产里有数据**。0 填充的 103 列直接丢弃即可。
- 20 新增列 336（多为带默认值的可空列，ETL 不需要供值）；类型变化 **18** 处（§4.2）。

### 4.1 必须给映射规则的删除列（有数据，按行数排序）

| 表 | 19 列 | 填充 | 20 去向 / 处置 |
|---|---|---|---|
| `account_move` | `checked` | 全量 | 20 改为 `review_state`（新增列）→ **需业务确认语义**，不能机械搬 |
| `account_move_line` | `deductible_amount` | 全量 | 20 改为 `deductible_percentage`：**金额→百分比，语义变了**，必须写换算规则并抽样复核 |
| `hr_version` | `employee_type` / `is_flexible` / `is_fully_flexible` | 2,502 | 20 为 `employee_type_id`（M2O）/ `fixed_term`；`is_flexible*` 无对应（快照字段，可从 `hr.employee` 重算） |
| `res_users_settings` | 5 列（push_to_talk 等） | 328 | 纯偏好，**丢弃** |
| `res_device_log` | 3 列 | 344 | 日志表，**丢弃** |
| `res_country` | `zip_required` | 251 | 20 无该列 → 丢弃（不影响业务） |
| `product_template` | `expense_policy` | 233 | 迁到 `res_company.sale_invoice_policy` 家族？需人工判定；先落 staging |
| `res_partner_bank` | `acc_number`/`acc_holder_name`/`sanitized_acc_number`/`bank_id`/`currency_id`/`has_iban_warning`/`has_money_transfer_warning` | 97 | 重命名映射 + `bank_id`→展平列 + **`currency_id` 无对应（丢弃需业务确认）**；后两个告警列在 20 合并为 `has_phishing_warnings`（compute，不迁）；`acc_number` 是密文列 |
| `product_category` | `complete_name` | 90 | 20 里 `product/models/product_category.py` 仍有 → 计算列，重算即可 |
| `payment_provider` | `state`/`color` | 25 | 20 payment 重构，按新 provider 模型重配（**支付通道需重登记**，与 B3 清单合并） |
| `resource_calendar(_attendance)` | `tz`/`schedule_type`/`two_weeks_calendar`/`flexible_hours`/`name`/`duration_days` | 1/15 | 20 为 `calendar_type`/`days_per_week`/`work_time_rate`/`reference_calendar_id`；工作日历**必须逐条转换**，否则排团工时算错 |
| `website` | `social_*`（8 列）+ `add_to_cart_action` 等 | 1 | `social_*` 迁到 `social_media` 模块（20 存在）；其余丢弃 |
| `mail_activity_type` | `chaining_type` | 13 | 20 为 `suggested_next_type_id` |
| `crm_stage`/`project_*_stage` | `color` | 4 | 20 移除阶段配色，丢弃 |
| `account_tax_group` / `res_company` | `tax_payable_account_id` 等 / `income_account_id`/`expense_account_id` | 2/1 | 20 走 `account.account.group` 模板路径，需在 B2 前定映射 |
| `fleet_vehicle` | `plan_to_change_car`/`plan_to_change_bike` | — | 20 合并为 `plan_to_change_vehicle`（布尔→选项） |
| `account_report`/`account_report_expression` | 多列 + `formula` varchar→text | 3 | 19 的新报表框架在 20 继续演进；**tour_accounting 自带抽象基类，不受上游影响**（计划 §7 A 箱判定成立） |

### 4.2 类型变化（18 处，ETL 需要显式 cast）

```
account_move_line.name            varchar -> text            （放宽，安全）
product_category.name             varchar -> jsonb           （变成翻译列：写 SQL 时须 ::jsonb）
website_page.url                  varchar -> jsonb           （同上，注意已有 .url 数据形态）
res_partner.name                  jsonb   -> varchar         （取消翻译：直拷即可）
res_company.name                  jsonb   -> varchar
hr_job.description                jsonb   -> text
res_groups_privilege.description  text    -> jsonb
project_task.partner_name         jsonb   -> varchar
iap_service.name                  varchar -> jsonb
sale_order_line.customer_lead     double  -> integer         （需 round，禁止截断静默）
resource_calendar.hours_per_week  float   -> numeric
ir_model_fields.index             boolean -> varchar
ir_act_client.params_store        bytea   -> text
其余 5 处见 /tmp/b0/diff_typechg.txt
```

## 5. 模块处置矩阵 —— 37 个第三方模块

判定列 = 在 Odoo 20.1a1 参考库上的**实测**试装结果（`-i` 单模块）。
「安全定义行」= `security/*.csv` 数据行 + XML 里的 `ir.rule` 记录数，即 F2 的重写面。

（下表由 `/tmp/b0/trial/verdict.tsv` + `/tmp/b0/matrix_thirdparty.md` 生成）

| 模块 | 归属 | 19 版本 | Py | JS | XML | 安全定义行 | 20 试装 | 首个失败原因 |
|---|---|---|---|---|---|---|---|---|
| `hr_custody` | Webkul OHRMS | 19.0.1.0.0 | 769 | 0 | 447 | 16 | FAIL | KeyError: 'ir.model.access' |
| `hr_employee_updation` | Webkul OHRMS | 19.0.2.0.0 | 453 | 0 | 136 | 4 | FAIL | KeyError: 'ir.model.access' |
| `hr_leave_request_aliasing` | Webkul OHRMS | 19.0.1.0.0 | 350 | 0 | 68 | 0 | **OK** | — |
| `hr_payroll_account_community` | Webkul OHRMS | 19.0.1.0.1 | 678 | 0 | 98 | 0 | FAIL | Model 'hr.leave.type' does not exist |
| `hr_payroll_community` | Webkul OHRMS | 19.0.1.0.1 | 2302 | 0 | 1942 | 19 | FAIL | Model 'hr.leave.type' does not exist |
| `hr_reminder` | Webkul OHRMS | 19.0.2.0.0 | 296 | 94 | 131 | 4 | FAIL | ParseError security/hr_reminder_security.xml |
| `hr_resignation` | Webkul OHRMS | 19.0.2.0.0 | 943 | 0 | 501 | 8 | FAIL | KeyError: 'ir.model.access' |
| `hr_reward_warning` | Webkul OHRMS | 19.0.2.0.0 | 474 | 46 | 352 | 7 | FAIL | ParseError security/hr_announcement_security.xml |
| `hrms_dashboard` | Webkul OHRMS | 19.0.2.0.0 | 1148 | 2183 | 1142 | 3 | FAIL | 同上（连带 hr_reward_warning） |
| `oh_employee_creation_from_user` | Webkul OHRMS | 19.0.1.0.0 | 135 | 0 | 15 | 0 | **OK** | — |
| `oh_employee_documents_expiry` | Webkul OHRMS | 19.0.2.0.0 | 691 | 0 | 431 | 8 | FAIL | KeyError: 'ir.model.access' |
| `ohrms_loan` | Webkul OHRMS | 19.0.2.0.0 | 1102 | 0 | 473 | 13 | FAIL | Model 'hr.leave.type' does not exist |
| `ohrms_loan_accounting` | Webkul OHRMS | 19.0.2.0.0 | 635 | 0 | 109 | 13 | FAIL | Model 'hr.leave.type' does not exist |
| `ohrms_salary_advance` | Webkul OHRMS | 19.0.2.0.0 | 794 | 0 | 338 | 9 | FAIL | Model 'hr.leave.type' does not exist |
| `tour_accounting` | 自研 tour | 19.0.4.11.0 | **16123** | 730 | **11325** | 104 | FAIL | `res.bank` comodel 不存在（连带 F2/F6） |
| `tour_base` | 自研 tour | 19.0.0.9.0 | 885 | 91 | 359 | 0 | FAIL | `res.bank` comodel 不存在 |
| `tour_budget` | 自研 tour | 19.0.1.0.1 | 340 | 0 | 429 | 9 | FAIL | ParseError security/account_budget_security.xml |
| `tour_cfo_portal` | 自研 tour | 19.0.1.0.0 | 337 | 0 | 641 | 12 | FAIL | `res.bank`（经 tour_accounting） |
| `tour_cmo_portal` | 自研 tour | 19.0.1.0.0 | 547 | 0 | 1002 | 10 | FAIL | `res.bank`（同上） |
| `tour_coo_portal` | 自研 tour | 19.0.1.0.0 | 571 | 0 | 834 | 14 | FAIL | `res.bank`（同上） |
| `tour_fleet` | 自研 tour | 19.0.1.1.0 | 296 | 0 | 317 | 3 | FAIL | `res.bank`（同上） |
| `tour_guide_portal` | 自研 tour | 19.0.1.0.0 | 562 | 0 | 1027 | 14 | FAIL | `res.bank`（同上） |
| `tour_hr` | 自研 tour | 19.0.2.0.0 | 30 | 0 | 97 | 0 | FAIL | ParseError（经 hr_reward_warning） |
| `tour_menu` | 自研 tour | 19.0.0.1.0 | 34 | 0 | 778 | 0 | FAIL | `res.bank`（同上） |
| `tour_operation` | 自研 tour | 19.0.0.9.0 | 696 | 0 | 623 | 4 | FAIL | `res.bank`（同上） |
| `tour_order` | 自研 tour | 19.0.0.4.0 | 736 | 0 | 1029 | 12 | FAIL | `res.bank`（同上） |
| `tour_pm_portal` | 自研 tour | 19.0.1.0.0 | 313 | 65 | 432 | 10 | FAIL | `res.bank`（同上） |
| `tour_product` | 自研 tour | 19.0.0.3.0 | 283 | 0 | 1011 | 14 | FAIL | `res.bank`（同上） |
| `tour_report` | 自研 tour | 19.0.0.2.0 | 200 | 0 | 273 | 1 | FAIL | `res.bank`（同上） |
| `tour_resource` | 自研 tour | 19.0.0.8.0 | 902 | 0 | 912 | 15 | FAIL | `res.bank`（同上） |
| `tour_saas` | 自研 tour | 19.0.2.0.0 | 543 | 0 | 186 | 2 | FAIL | `No module named 'odoo.service.db'` |
| `tour_shopping` | 自研 tour | 19.0.0.5.0 | 259 | 0 | 254 | 6 | FAIL | `res.bank`（同上） |
| `tour_tourist_portal` | 自研 tour | 19.0.1.1.0 | 680 | 0 | 1234 | 12 | FAIL | `res.bank`（同上） |
| `tour_tutor` | 自研 tour | 19.0.0.1.0（未装） | 229 | 0 | 343 | 0 | FAIL | `res.bank`（同上） |
| `tour_website` | 自研 tour | 19.0.0.1.0 | 699 | 0 | 789 | 3 | FAIL | `res.bank`（同上） |
| `tour_website_sale` | 自研 tour | 19.0.0.1.0 | 431 | 40 | 149 | 0 | FAIL | `res.bank`（同上）+ F6 OWL 重写 |
| `web_responsive` | OCA | 19.0.1.1.0 | 199 | 2514 | 734 | 0 | **OK** | — |

### 5.1 处置结论（port / replace / abandon）

| 组 | 模块 | 处置 | 依据 |
|---|---|---|---|
| G-门户链 | tour_base + 其余 19 个 tour_* | **port**，且必须先做两件共享前置：① `tour.bank.account` 去 `res.bank` 化（**已改道**：新建自有 `tour.bank` 主数据模型，见 §5.2-S1）② 全量 security → `ir.access` | §3-F2/F3；前置未做时后面每个模块的深层错误都看不见 |
| G-payroll | hr_payroll_community / hr_payroll_account_community | **abandon（本期）** | 20 假勤重构（F5）+ 生产是否真在用工资单待业务确认；确认前不排工作量 |
| G-loan | ohrms_loan / ohrms_loan_accounting / ohrms_salary_advance | **port，阻塞于 F5** | 同样引用 `hr.leave.type` |
| G-HR 其余 | hr_custody, hr_employee_updation, hr_reminder, hr_resignation, hr_reward_warning, hrms_dashboard, oh_employee_documents_expiry | **port**（主要是 F2 的 security 重写） | 首失败全部是 ir.access 类 |
| G-已可用 | hr_leave_request_aliasing, oh_employee_creation_from_user, **web_responsive** | **直接复用**（只改版本号） | 实测 `-i` 通过 |
| G-SaaS | tour_saas | **abandon**（计划 §7 已定） | F4 |
| G-前端 | tour_website_sale | **port + OWL 重写** | F6 |

### 5.2 B1 前置原型实测（2026-09-21，基线 alpha 20.1a1）

工具：`c-系统实现/tms-platform/scripts/migration/security_19to20/`（README 含复现命令）。
实验全部在 `/tmp` 副本 `b1addons` 与一次性数据库 `b1sec1..7` 上完成，**未改动 `addons/` 生产源码**。

| 步骤 | 动作 | 结果 |
|---|---|---|
| S1 | `tour_base` 去 `res.bank` 化：**新建自有模型 `tour.bank`**（name/bic/country/state/地址），`tour.bank.account.bank_id` 改指它 | 由"改挂 `res_partner_bank` 展平列"改道。理由：`res_bank` 在 19 仅 60 行，被两处外键引用（`res_partner_bank.bank_id` 48/97 有值、`tour_bank_account.bank_id` 72/72 全有值）；同 ID 复制到新表 ⇒ `tour_bank_account.bank_id` 一个值都不用改，而挂 `res_partner_bank` 会把"开户行主数据"和"往来账户"两种语义混在一起。`tour_base` 空库 `-i` **通过**（43.7 s，29 模块） |
| S2 | 以 19 现网为权威源生成 ir.access（v1：逐行复制） | 1,561 行 / 106 个 owner 模块 —— 但其中官方模块的行是重复授权，故改 v2 |
| S3 | v2：与 20 core 的 2,429 个 (模型,组) 授权做差 + 拆宽行 | **696 行**：官方组差量 283、规则行 264、自定义组全量 125、全局限制 22（另有 93 条与 core 完全重复，已自动去重）；`tour_security_bridge` 桥接模块承载官方组差量（522 行，depends 66） |
| S4 | 逐模块替换：删 `ir.model.access.csv`、剥离 XML 里的 `ir.rule`/`ir.model.access` 记录、manifest 改指 `security/ir.access.csv` | 24 个自有模块，共写入 213 行规则/宽授权，剥离 62 处 XML 记录 |
| S5 | 全链路空库安装 `-i tour_security_bridge`（168 模块） | 见下方里程碑 |

**里程碑（阻塞阶梯，逐层实测）**：

| 轮次 | 进度 | 首个失败点 | 失败原因 | 结论 |
|---|---|---|---|---|
| R1 | 106/169 | `tour_budget/views/account_budget_views.xml:203` | `Forbidden owl directive used in arch (t-esc)` | 新工作包 ①QWeb 指令 |
| R2 | 117/168 | `hr_employee_updation/views/hr_employee_views.xml:4` | xpath `//page[@name='payroll_information']//field[@name='contract_type_id']` 在 20 的 `hr.employee` 表单中不存在（页签在、字段已移走） | 新工作包 ②Webkul 视图继承断裂 |
| R3 | 117/159 通过 → 127/159 | `hr_custody` `report.custody.init()` | `AttributeError: 'report.custody' object has no attribute '_cr'` | 新工作包 ③遗留 API |
| R4（剔除 OHRMS，只跑 tour 链） | **127/138** | `tour_accounting/data/data_fixes.xml:17` | `<function model="account.financial.report" name="_fix_financial_report_data">` 执行失败（模型由 tour_accounting 自带：`report/report_financial.py:29`） | 阻塞点已推到 tour_accounting 的报表数据层，即 §5.1 A 箱最重的一块 |

R4 之前 **`tour_base`、`tour_budget`、`tour_product`、`tour_resource`、`tour_order`、`tour_fleet`
与 `hr_reminder`、`hr_reward_warning` 全部在 20 空库安装成功** —— 说明
①权限层转换成立，②`res.bank` 解耦成立，③B0 判断的"两个共享前置挡住后面所有模块"得到验证。

**三类新工作包（原计划未量化）**：

1. **QWeb 指令**：20 的 arch 校验白名单（`ir_ui_view._validate_qweb_directive`）不再允许
   `t-esc` / `t-raw`，官方统一改成 `t-out`。现网自有模块 **560 处 / 23 文件 / 14 模块**
   （另有 480 处已在用 `t-out`）。机械替换即可，但属"批量改动生产模板"，须单独提交、单独回归。
2. **Webkul 视图继承断裂**：上游 20 把 `contract_type_id` 一类的字段从 `hr.employee` 表单移走，
   Webkul 的 xpath 失去锚点。G-HR 其余 7 件的"只需重写 security"结论**偏乐观**，
   需按视图逐个复核继承点（`hr_employee_updation`、`hr_custody` 已各中一处）。
3. **遗留 API**：`self._cr / _uid / _context` 在 20 的模型上彻底消失
   （实测：19 `hasattr(AbstractModel,'_cr')=True`，20 = False；`api.Self`、`api.deprecated`
   同样只在 19 存在）。**本节结论按 `scripts/migration/check_legacy_api.py` 重测修正**：
   自有 tour_* 代码 **0 处**，全部 19 处（`self._cr` 13 + `self._context` 6）都在 Webkul 的
   `hr_custody`（3 文件）与 `hrms_dashboard`（2 文件）里 —— 早先记的"自有代码 61 处 / 6 模块"
   是把 `self.env.cr`（现网 96 处）一起 grep 进去了，作废。
   这些替换（`self._cr` → `self.env.cr`）在 19 里同样合法，属**双兼容改动**，可先回落 19 分支当天回归。
   另有 `from odoo.http import content_disposition` → 20 移到 `odoo.http.stream`
   （现网仅 `tour_accounting/controllers/statement_report.py` 2 处，已在副本中改通）。

### 5.4 空库装载阶段新增的硬事实（2026-09-22，`tour_accounting` 首个装绿）

`tour_accounting` 连同 5 个依赖在 20 空库 `-i` **全绿**，过程中确认 4 条此前未知的行为差异，
每条都会影响 B2 的 ETL 写法：

* **20 会在建科目时自动建日记账**：`account.account.create()` → `_create_default_journals()`
  （`account_account.py:1141`）对 `asset_cash` / `liability_credit_card` 造 bank/cash journal，
  多个现金科目会撞 `mail.alias` 唯一约束（`Alias bank-none … already linked with Journal`）。
  19 无此逻辑。**ETL 硬规则：科目必须走 SQL 直插，不能走 ORM `create()`**，
  否则 20 会凭空造出生产上不存在的日记账；模块自带种子数据统一挂
  `context="{'skip_auto_account_journal_creation': True}"`（`tools/convert.py` 的
  `get_env()` 支持节点上的 `context`，可写在 `<odoo>` / `<data>` 根节点上按文件生效）。
* **`post_init_hook` 签名**：19 与 20 的 `loading.py` 都是 `post_init(py_module)(env)` —— 传的是
  **Environment 不是 cursor**。`tour_accounting/hooks.py` 用 `hasattr(x,'cursor')` 嗅探，两版都恒为
  False，落到 `api.Environment(env, …)` 后撞 20 新增的 `assert isinstance(cr, BaseCursor)`。
  改成 `isinstance(x, api.Environment)`（也是双兼容写法）。
  副作用记录：该 hook 在 19 现网确实产出过 7 个 `CC-*` + 213 个 `PC-*` 分析账户，
  而 20 空库新装时部门和线路都为空 → hook 是 no-op，这批数据必须由 ETL 带（象限 2/3）。
* **翻译列 jsonb/varchar 血统**：`orm/fields.py:891` 对 `translate`/`company_dependent` 字段返回
  `('jsonb','jsonb')`，但**已存在的列不会被改类型**。从早期 scratch 库克隆出来的库是 varchar，
  装 tour_* 时 `ORDER BY res_company.name->>'en_US'` 直接报
  `operator does not exist: character varying ->> unknown`。
  **方法规则（不是可选项）：B1 的度量库必须由"同一条命令新建"，不许从旧 dev 库克隆。**
* **20 删掉的对象补充确认**：`account.group`（19 现网表 0 行，fork 自己也没声明过该模型，
  其 `data/account_account_tour.xml` 甚至注明"无 account.group 时科目为平铺"）、`res.bank`、
  `hr.leave.type`（20 `hr_holidays` 只有 `hr.leave`/`hr.leave.allocation`/`hr.leave.accrual.level`/
  `hr.leave.mandatory.day`）、`ir.actions.report.report_file` 字段（非存储 → 列级 diff 看不见）。
  消失的核心 menu xid：`account.root_payment_menu`、`account.account_logs_menu`、
  `account_payment.{payment_token,payment_method,payment_transaction}_menu`、
  `hr_expense.menu_hr_expense_account_employee_expenses`。

配套的三个静态预检脚本（`check_xmlid_order.py` / `check_model_refs.py` / `check_field_refs.py`）
与新加的 `check_legacy_api.py` 用法见 `c-系统实现/tms-platform/scripts/migration/README-空库预检.md`。

**未通过 Gate B1 的部分**：`tour_accounting`（卡在上面 R4 的数据修复函数）、其下游 7 个 portal 模块、
`tour_website_sale` 尚未跑到；`hr.leave.type` 相关的 G-loan/G-payroll 仍按 §5.1 结论阻塞；
`tour_saas` 在第 108 个模块处以 `ModuleNotFoundError: odoo.service.db` 复现失败 —— 与 CR-01 一致，
原型中已从 addons 副本与桥接依赖里剔除（其 1 条权限行并入桥接）；`tour_hr` 因依赖 OHRMS 而无法独立验证。

**据此修正 §9 的 B1 工作量**：权限层由"12–16 人日"降到 **6–9 人日**（工具已覆盖 80% 机械部分，
剩 86 条人工裁决 + `noupdate`/覆盖上游行的归属设计）；新增 ①QWeb 指令 **1–2 人日**、
②Webkul 视图继承复核 **+3–5 人日**、③遗留 API **1–2 人日**；
`tour_accounting` 报表数据层 **仍按 §7 的 10–18 人日**，但现已给出确切入口
（`data/data_fixes.xml` 的 `_fix_financial_report_data` + `report/report_financial.py`）。


## 6. 11 个「20 社区版已删除」的官方模块

| 模块 | 已装 | 20 侧事实 | 处置 |
|---|---|---|---|
| `hr_org_chart` | 是 | 功能并入 `hr`（`addons/hr/controllers`） | 无需动作，菜单来自 hr |
| `hr_hourly_cost` | 是 | `wage` 已在 `addons/hr/models` | 无需动作 |
| `hr_homeworking` / `hr_homeworking_calendar` / `hr_holidays_homeworking` | 是 | `hr.work.location`/`hr.employee.location` 已在 `hr`（`hr/models/res_users.py`），但 20 全树仅剩测试引用 → 远程办公日程功能**降级/移出社区版** | 需业务确认是否使用；若用则 replace（自研薄模块）或接受降级 |
| `website_sale_wishlist` | 是 | `product.wishlist` 已并入 `website_sale` 核心 | 无需动作 |
| `website_sale_comparison` / `_comparison_wishlist` | 是 | 20 社区版无 `comparison` 模型 | abandon（无数据：`product_wishlist` 0 行，比对功能同理） |
| `website_sale_autocomplete` | 是 | 20 无该模块 | abandon 或 replace（地址自动补全，需业务确认） |
| `account_add_gln` | 是 | 仅 `l10n_es_edi_facturae` 有 gln 字段 | abandon（西语 EDI 用不到） |
| `iot_base` | 是 | 20 社区版无任何 `iot*` 模型 | abandon（生产无 IoT 设备；确认后卸载） |

数据佐证：`product_wishlist` **0 行**、`hr_employee_location` **0 行**、`hr_work_location` **3 行** ——
这 11 个模块里真正带业务数据的只有 3 条工作地点记录。

## 7. ETL 设计增量（在计划 §8 四象限之上，B0 新结论）

1. **象限 3 新增「权限重写子步骤」**：`ir_model_access`（19 现网实测 1,405 行）+ `ir_rule`（431 行）
   → 生成 `ir.access` 行；已按此实现转换工具
   `c-系统实现/tms-platform/scripts/migration/security_19to20/`（导出 → diff 20 core → 生成
   各模块 `security/ir.access.csv` + 桥接模块；v2 原型 696 行 / 桥接 522 行 / 复核 86 项，
   **该组数字已随 v3 作废**），见 §5.2-S2。这是纯规则转换（operation=crud 映射 +
   `domain_force` → `domain`），但**必须逐条人工复核**，因为它决定门户可见性。
   关键语义：20 中带 `group_id` 的 permission 行是 **OR**、无 group 的 restriction 是 **AND**，
   所以 19 的"宽授予 + 记录规则收窄"**不能只在 security 文件里加 restriction**，
   必须同一步把宽授予收窄，否则访问面静默扩大。
   **v2 逐条平移有一处语义错误已修正**：19 的组成员继承父组授予、记录规则按用户所属任意组匹配，
   因此"规则挂在没有 access 行的组上"（v2 判为 inert 的 77 条）其实**生效**——
   丢弃=静默收窄（如 `crm.lead` 的 All Leads 会让"看全部线索"的人退回只看自己），
   当 restriction 平移=静默放宽。v3 改为**按人群重建有效权限**
   （`classify_rules.py`：全局规则→restriction 行、组规则→带 domain 的 permission 行；
   多规则人群的 domain 合并借用 **20 自己的 `odoo.orm.domains.Domain`** 做，前缀记法 arity
   由引擎保证，出站逐条自检 0 条不可解析）。实测 permission 1,407 + restriction 117 行 /
   626 模型，待复核由 86 降到 **14**（NO_GRANT_POP 12 + CTX_OUT_OF_20 2）。
   附带一条硬事实：20 的 access domain 可求值上下文**只有** `user/time/company_id/company_ids`
   （`ir_access.py:312 _eval_context`），19 里用到 `website`/`uid`/`object` 的域 B1 必须改写
   （落库后是 NameError 报错，不是静默放行），详见该目录 README。
   **装载验证（2026-09-21，scratch 库 `b1sec7`）**：作用域裁剪后的 188 行
   `security/ir.access.csv` 装进真实 20 registry **0 ERROR**、domain 40 行全部落库；
   行为探针（`probe_bridge.py`，shell 退出即回滚）证实 domain 在查询期生效 ——
   portal 用户对 `tour.guide` 2 条只见 1 条、域外 `read()` 报 `AccessError`、
   superuser 对照见 2 条；`res.partner.bank` 的**带点关系路径**域
   （`partner_id.employee_ids = False`）在 20 也可用。
   这一轮同时抓出 §3-F2 说的 `operation` Selection 顺序缺陷（修复前 959/1,524 行装不进去）：
   **文本层面完全看不出来，转换层必须过一次真实装载才算验证。**
   生成器已补三道门（`--target-models` / `--target-groups` / `--installed-modules`），
   按**目标库实际状态**把行分成"现在可装 / 延后"两份并自动算 depends + 写 manifest：
   只按 model→module 归属推断会误判（19 把 `hr.contract.type` 记在 `hr` 名下、20 归独立的
   `hr_contract`），只按模型存在也不够（depends 里出现尚未就位的 `tour_website_sale`
   → `Failed to load registry`）。v2 桥接层装不起来正是栽在第二条。
   验收判据：A1 用的登录/权限矩阵（`d-交付验收/A1-平桥验收报告_2026-09-21.md` §5）在 20 上结果一致。
2. **象限 1 的 `account_move*` 需两处列映射**：`checked→review_state`、
   `deductible_amount→deductible_percentage`。**禁止默认换算**：先在 staging 上重算并与 19 报表逐户比对，
   再由财务签字确认换算式，否则总账出数会有系统性偏差（这条直接进 B2 对账判据）。
3. **附件/银行账号**：`res_partner_bank` 走象限 1（整表 + 保 ID + 重命名 4 列 + 展平 `bank_id`），
   密文列处理必须在 staging 完成并校验（A0-2 的密钥一致性前置）。
4. **工作日历**：`resource_calendar*` 从象限 3 提到**象限 2**（走 ORM `create()`），
   因为 20 的 `calendar_type/days_per_week/work_time_rate` 有 compute 约束。
5. **类型 cast 清单**（§4.2 的 18 条）写进每模型映射 yaml，作为 `etl_load` 的强制声明；
   未声明的列类型变化一律 **报错而不是隐式转换**。
6. `res.users` 创建会自动建 `hr.employee`（A1 的 K12）→ 象限 2 的用户搬迁必须走
   「先建 partner+user，再回填 employee 关联」的顺序，不能直拷后加约束。
7. **`res.bank` 消亡 → 自有 `tour.bank` 主数据（象限 3，保 ID 直拷）**。20 已删除 `res.bank` 模型，
   §5.1 已定：改为 B1 新建自有 `tour.bank`（字段沿用 `res.bank` 的 name/bic/street/street2/zip/city/
   phone/email/country/state，见 §5.2-S1）。现网实测规模：`res_bank` **60 行**、
   `tour_bank_account` **72 行且 `bank_id` 72/72 全部有值**、`res_partner_bank` 97 行（`bank_id` 48 行有值）。
   搬迁规则：
   - `INSERT INTO tour_bank (id, name, bic, street, …) SELECT id, name, bic, street, … FROM 19.res_bank`
     **保留原 ID 并 `setval` 序列** → `tour_bank_account.bank_id` 列名与取值都不必改写，
     只需在 20 侧把该列的 FK 目标改成 `tour_bank`（模型定义阶段就是新 FK，无需 UPDATE 业务行）。
   - 对账判据：`count(tour_bank)=60`、`tour_bank_account.bank_id` 悬空引用 0、抽样 10 条账户的
     开户行名称与 19 逐字一致。
   - `res_partner_bank.bank_id`（48 行）不再走 FK，展平写入 20 的 `bank_name`/`bank_city`/
     `bank_bic`/`country_id` 列；余下 49 行本就只填了 `bank_name` 自由文本，原样直拷。
     展平取值优先级：`bank_id` 指向的主数据 > 已有 `bank_name` 文本（后者不可被空串覆盖）。

## 8. 复现命令

```bash
# 19 侧
docker exec tms-db psql -U odoo -d tms -At -F'|' -c \
 "select table_name,column_name,data_type,coalesce(character_maximum_length::text,numeric_precision::text,'') \
  from information_schema.columns where table_schema='public'" > cols_19.tsv
# 20 侧参考库（一次性）
cd /home/adai/odoo20 && ./.venv/bin/python odoo-bin -c odoo.conf -d b0snap20 --no-http \
  --stop-after-init --without-demo=all -i base,web,mail,portal,contacts,analytic,product,account,\
account_check_printing,fleet,hr,hr_expense,project,sale,crm,website,website_sale
# 第三方试装（版本号需先改成 20.1.x；pandas/qifparse 用 PYTHONPATH 注入临时目录）
cp -r c-系统实现/tms-platform/addons /tmp/b0/tp20addons          # 只改副本
PYTHONPATH=/tmp/b0/pylibs ./.venv/bin/python odoo-bin -c odoo.conf -d b0snap20 \
  --addons-path="odoo/addons,addons,/tmp/b0/tp20addons" --no-http --stop-after-init \
  --without-demo=all -i <单个模块>
```

> 注意：`--without-demo=all` 在 20 会有 `invalid boolean value: 'all', assume True` 的告警，
> 语义仍是「全部不装演示数据」，暂不处理。

## 9. B1 工作量重估（据 §3–§5）

| 工作包 | 原估 | B0 后 | 依据 |
|---|---|---|---|
| 权限层 `ir.access` 重写（36 模块 / ~390 处定义） | 含在 30–60 内 | **12–16 人日** | F2；tour_accounting 一家 104 行 |
| `tour.bank.account` 去 `res.bank` + 银行账号 ETL | 未识别 | **4–6 人日** | F3；连带密文列 |
| tour_* 其余适配（视图/字段/报表入口） | — | 10–18 人日 | tour_accounting 16k Py + 11k XML 为主 |
| OHRMS 13 个（除 2 个已 OK） | — | **暂不可估** | F5：20 假勤重构映射未定；先做 1 人日 spike |
| tour_website_sale OWL | 3–5 | 3–5 | F6 |
| tour_saas 停用 | 0 | 0 | F4 |
| **合计 B1** | 30–60 | **30–45 人日 + OHRMS 待 spike 后追加** | |

**B0 gate 判定：通过**（矩阵与 diff 报告成文、B1 范围据此冻结）。
**遗留需业务确认（不阻塞 gate，但阻塞 B1 开工）**：
① `hr_payroll_community` 生产是否真在用（决定 7 个 OHRMS 模块的去留）；
② `checked→review_state`、`deductible_amount→deductible_percentage` 的财务语义确认；
③ 远程办公/工作地点（hr_homeworking、hr_work_location 3 行）是否可降级；
④ 支付 provider（`payment_provider.state`）在 20 的重新配置。
