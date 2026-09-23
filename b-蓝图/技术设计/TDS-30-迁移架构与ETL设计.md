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
- **F5 `hr.leave.type` 模型消失**：20 全树 0 引用（已复核：`addons/` + `odoo/` 全源 grep = 0 命中），
  `hr_holidays` 重构后只剩
  `hr.leave` / `hr.leave.allocation` / `hr.leave.accrual.*` / `hr.leave.mandatory.day` 等。
  → Webkul 的 4 个模块（hr_payroll_community、hr_payroll_account_community、ohrms_loan*、
  ohrms_salary_advance）报 `TypeError: Model 'hr.leave.type' does not exist in registry`。
  **替代概念已查明（2026-09-22）**：20 的"请假类型"就是 `hr.work.entry.type`，
  `hr.leave.work_entry_type_id`（20 `hr_holidays/models/hr_leave.py:167`）取代了 `holiday_status_id`，
  类型上的策略字段（是否扣假/计薪/需批准）改挂在 work entry type 上。
  这不是改名而是**语义重构**：19 的 `hr.leave.type` 上有 ~40 个字段与 3 个策略方法，
  Webkul 那些模块引用的是"类型"这层业务对象，映射到 20 需要逐点决定"落到 work entry type"
  还是"落到一个自建模型"。⇒ **OHRMS 假勤链的移植工作量在签字前不要估算**（G-loan 同）。
  B1 gate 的实际影响已量化：20 个 tour_* 里**只有 `tour_hr`** 通过
  `hr_resignation/ohrms_loan/hr_reward_warning/oh_employee_documents_expiry` 拉进这条链，
  其余 19 个可以在空库上单独跑 gate（见 §5.7）。
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


### 5.5 Webkul OHRMS 在 20 的可装性实测（2026-09-22）

14 件 OHRMS + web_responsive 逐个在 20 空库试装，结论不是"整块不行"，而是**单一结构性阻塞点**：

| 结论 | 模块 |
|---|---|
| 20 空库可装（仅需遗留 API 机械改写） | `hr_employee_updation`、`oh_employee_documents_expiry`、`hr_reward_warning`、`hrms_dashboard`、`hr_custody`、`html_editor`、`html_builder`、`web_responsive` … |
| **阻塞** | `hr_payroll_community` —— 视图引用 19 的 `hr_holidays.edit_holiday_status_form`，而 20 把 `hr.leave.type` **整个模型删了**（不是改名：20 全树零引用），`hr.leave` 也去掉了 `holiday_status_id`，换成 `work_entry_type_id` |
| 被上面连带阻塞 | `ohrms_loan`、`hr_resignation`（`depends` 里有 `hr_payroll_community`）→ 连带 `tour_hr` |

**关键判据 —— 要移植的不是代码，是"根本没有的锚点"**：19 现网 `hr_leave_type` 73 行有值，
但 `hr_leave` / `hr_payslip` / `ohrms_loan` / `hr_resignation` / `hr_custody` 的业务行**全为 0**。
即工资单的"请假→薪资"逻辑在 20 侧既无模型可挂、也无数据要迁。
→ 移植 = 在 20 上重写一个不存在的字段语义，**砍掉 payroll/loan/resignation 的实际业务损失为 0**；
保留 `hr_custody`（可装）与考勤/文档/奖惩类（可装）。**此为待业务签字的范围决定**，不由技术侧单方判定。

配套的两条工具结论（已写进预检脚本）：

* QWeb **模板子树**里的 `groups=` / `t-out` 引用是**渲染期**解析，判成装载期缺陷是误报
  （`report/multiple_invoice_report_template.xml:115` 那两个
  `account.group_show_line_subtotals_tax_{excluded,included}` 实测在 **19 现网和 20 都不存在**，
  是从 Cybrosys fork 继承来的死分支，不是 19→20 回归）；
  但 `<template inherit_id="…">` 例外 —— `_tag_template` 把它转成
  `<field name="inherit_id" ref="…">`（`tools/convert.py:529`），是**装载期**解析。
* `website.default_website` 在 20 变成 `base.default_website`，且由
  `website._ensure_default_website_consistency`（`website.py:468`）**惰性登记**
  → 任何直接 `ref()` 它的种子数据都必须改成容错写入（本次用 `tour_website` 新增的
  `_tour_write_brand_name`：`search([], limit=1, order='sequence, id')`）。


### 5.6 单测驱动测出的 19→20 语义变更（两批：财务链路 + 资源/车队，2026-09-22）

判据来源：`b1tour1`（20 空库装 19 个 tour_*，121 模块）**一次性跑 `--test-tags /tour_accounting`**。
起点 78 测试 / 27 错，终态 **82 测试 / 0 错**。逐个错都是"实测出来的差异"，不是猜测：

| # | 19 的行为 | 20 的行为（实测证据） | 影响与处置 |
|---|---|---|---|
| 1 | `ir.model.access` + `ir.rule` 两张表 | 合并成 `ir.access`（表 `ir_access`），4 个 `perm_*` 位 → 一个 `operation` 串 | 已建的 `security_19to20/` 转换必须**以目标库真实 registry 为唯一装载判据**：早先那次用小的 target-models 清单生成，tour_accounting 100 行只剩 52 行，报表向导的授权全被"延后"，直接表现为 17 个 `You are not allowed to create …` |
| 2 | 规则域 `domain_force` **装载期不校验字段** | `ir.access` CSV 装载期就用真实 registry 求值域 | 19 里躺平的死域（`tour.plan.reg.partner_id` 由 `tour_website` 追加，而授权行在 `tour_accounting`）在 20 变成**整批装载失败**。新增 `security_19to20/check_domains.py` 做静态预检；跨模块的域规则只能落到"依赖两边"的桥接模块（本次新建 `tour_sec_bridge7`） |
| 3 | `SQL.code` / `SQL.params` | 合成 `SQL._sql_tuple = (code, params, to_flush)`（`tools/sql.py:96`） | 全仓 1 处（`account_move_line._query_get`）；已加进 `check_legacy_api.py` 规则表 |
| 4 | `ir.config_parameter.get_param/set_param` | **只有带类型的** `get_str/get_bool/get_int/get_float` + `set_*`（`base/models/ir_config_parameter.py:66-131`） | tour_* 23 处已全部改写；剩余 13 处全在 Webkul 包（等 payroll/loan 范围决定）。**ETL 好消息**：20 的 `value` 仍是「字符串化 Text + 读时 `_convert`」，19 搬来的 `'True'`/`'5000.0'` 无需改写 |
| 5 | 汇率按 `name <= date` 取 | 按 **`name < date`** 取（`base/models/res_currency.py:186` vs 19 的 `:127`） | **业务语义变更，不只是代码问题**：某天发布的汇率当天不生效，次日才生效。月末重估、"当天录汇率当天开单"都会差一天。测法：`_convert(100, …, '2020-06-01')` 在只有 06-01 汇率时 19 给 25、20 给 50。→ 写进 UAT 已知问题；`res.currency.rate` 象限 3 搬迁时要不要整体前移一天，需业务确认 |
| 6 | `account.move.line.name` 由 `_compute_name` 用产品名填充 | 同样有 compute，但**实测为 `False`**（`display_type='product'`、`product_id` 有值时仍空） | 不是测试问题：`asset_create` 拿 `record.name` 当资产名（NOT NULL）→ 「采购发票自动生成固定资产」在 20 必炸。已在模型侧改为 说明 → 产品名 → 单据号 三级兜底 |
| 7 | m2m 写入不校验目标模型权限 | 写入后对**新增记录** `check_access('read')`（`orm/fields_relational.py:1574-1582`），失败即 `Failed to write field …` | `account.move.tour_plan_ids` 在冲销（`_reverse_moves`→`copy`）时被复制 → 会计组需要 `tour.plan` 的 **read**（19 现网确实没有这条授权）。已补 3 行到 `tour_accounting/security/ir.access.csv`，**属权限面扩大的范围决定，待业务签字** |
| 8 | m2m 带 `comodel_domain` | 20 起 `invoice_line_ids` 限定 `display_type in (product, line_section, line_subsection, line_note)` | 任何手工构造发票行的脚本/ETL 都要显式给 `display_type`，否则报 `Cannot link inaccessible records` |
| 9 | `account.account.company_id` | **字段没了**，改成 `company_ids`（m2m） | 所有按公司筛科目的裸 SQL/域都要改；ETL 象限 3 的 `account_account` 需带 `account_company_rel` |
| 10 | `account.move.invoice_currency_id` | **字段没了**，统一用 `currency_id` | 同上，属 B2 映射表条目 |
| 11 | — | `UPPER(jsonb)` 在 PG 里不存在 | `report_aged_partner.py` 的 `UPPER(res_partner.name)` **在 19 现网同样是死代码**（`name` 两侧都是 jsonb），是 Cybrosys fork 带进来的潜伏缺陷，只有单测打到它才暴露。已改成 `UPPER(coalesce(name->>'en_US', name #>> '{}'))`（该表达式在 19 现网数据上实测可跑）。**建议同步回 19 生产**：账龄分析 xlsx 只要走到这条 SQL 就会报错 |

第二批判据来源：同一 `b1tour1` 跑 `--test-tags /tour_fleet,/tour_resource`（39 测试），
起点 **32 错** → 修完两组语义变更后 **0 failed / 0 error of 39**。这一批暴露的是**财务链路之外**的问题：

| # | 19 的行为 | 20 的行为（实测证据） | 影响与处置 |
|---|---|---|---|
| 12 | `BaseCommon` 用 admin 跑用例（19 `base/tests/common.py` 只有 `cls.env.user.group_ids += cls.get_default_groups()`，而 admin 本身已在全部组） | `BaseCommon` 声明 `_test_user_groups = ('base.group_user',)`（`odoo/addons/base/tests/common.py:18`），`_callSetUp` 把 `self.env` 重绑到一个**只有内部用户组的 Test User** | 表现为 32 个 `AccessError`（tour.guide/supplier/driver、resource.resource 的读写）。**这不是产品缺陷，是测试夹具变更**；但顺带暴露了真实事实：19 现网的 admin 是被**手工**加进 计调/导游管理/财务 三组的（`tour_accounting/security/security.xml:41,49` 还把 `user_root/user_admin` 加进两个会计组），所以"19 测试能过"依赖的是生产数据里的组关系 → **B2 必须把 `res_groups_users_rel` + `res_groups_implied_rel` 当迁移数据搬**，否则 20 上业务角色照常缺权。已按最小授权给三个测试类补 `_test_user_groups = ('base.group_user','tour_base.group_tour_manager','hr.group_hr_user')` |
| 13 | `read_group(domain, fields, groupby, orderby=…, lazy=…)` → **`list[dict]`**（19 `orm/models.py:2749` 文档串里就写着 "Deprecated"） | `read_group` 与 `_read_group` **同形状**：`(domain, groupby=(), aggregates=(), having=(), order=…)` → **`list[tuple]`**（值序 = groupby 后接 aggregates，m2o 分组给 `id`、m2o 聚合给 `ids`；aggregates 必须带聚合函数 `'x:sum'`，裸名里**只有 `__count` 合法**（`'recordset'` 也得写成 `'x:recordset'`），否则 `ValueError: Aggregate method is mandatory for 'x'`，`orm/models.py:1931-1995 / 2086-2103`） | **本会话最高危**：`fields=`/`orderby=` 已不存在（关键字写法必 `TypeError`），但**位置写法不报错、只是数错**——第三个位置参数被当成 `aggregates`，`g['x_count']` 全部取不到。实测调用点 **19 处 = tour_\* 18 + Webkul 1**（tour_cmo_portal 9、tour_base/tour_dashboard 3、tour_resource/tour_guide 3、tour_product/tour_line 2、tour_pm_portal 1；Webkul 那处在 `hr_payroll_community/models/hr_employee.py`，等 payroll 范围决定）。tour_* 已全部改为 `_read_group(domain, groupby, aggregates)` 元组解包；`check_legacy_api.py` 加了 4 条**必须跨行匹配**的检测规则（19 关键字 `fields=/orderby=/lazy=` ／ aggregates 位是裸字段 ／ 结果按字符串 key 取值 ／ `<groupby>_count`），对照验证：未改树 31 条调用+取值命中、已改树 tour_* 归零（只剩 Webkul 那 1 处）。按行匹配曾在 18 个真实缺陷上报 **0**，这类"检查器说没事"比没检查更危险，故规则单独走 `_scan_read_group`。**20 规范写法**见 core：`Model._read_group(dom, ['field_id'], ['__count'])` + `for rec, count in ...` |
| 13b | 同上，`tour_pm_portal/controllers/portal.py:172` 的分组串写成 `'month:begin_date'`，取值用 `item.get('begin_date:month')` | — | **19 现网潜伏缺陷**：键名写反，`get` 恒为缺失 → 项目经理门户的"月度趋势"**月份列一直为空**（数字也拿不到）。改 20 API 时顺手写成 `['begin_date:month']` + `order='begin_date:month asc'` 并保留注释。**建议同步回 19 生产**，别等 B3 |
| 14 | `tour.line` 用 `_inherits` 委托 `product.template`；计调/经理账号在建线路、建项目时**依赖手工授予的管理员组** | 19/20 上游一致：`product.template` 的 create 只给 `product.group_product_manager`（19 csv 里 `access_product_template_user,…,base.group_user,1,0,0,0` = 只读；20 侧 product.template **唯一**的无组 `ir_access` 行是 `product.product_comp_rule` 多公司记录规则，不是授权），`project.project` 的 create 只给 `project.group_project_manager` | 空库 + 最小 Test User 跑出来的 **3 个 AccessError 全在这里**，与 19→20 无关（19 DB 里产品模型也没有任何 `group_id is null` 的授权行，已实测比对）。但它坐实了 #12：**"现网计调能新增线路"不是模块授权，是 admin 被手工加进了产品管理员/项目经理组**。⇒ ① `res_groups_users_rel` 属 B2 必搬数据；② 20 的授权矩阵要么补一条 product/project create 给 tour 经理组（业务签字，属功能变更），要么在切换后由管理员重新手工加组 —— 二者都必须在 runbook 里有名字，否则切过去就是"线路不能新建"这种看起来像迁移事故的现象。测试夹具已按上游事实补 `product.group_product_manager` / `project.group_project_manager` 并注明理由 |
| 15 | `odoo/http.py` 是**单文件模块**，公开名 131 个（`content_disposition`、`serialize_exception`、`Session`、`db_list`、`werkzeug` … 全在 `odoo.http` 命名空间里） | 20 把它拆成**包** `odoo/http/`（`__init__.py` 只有 21 行），**不再重新导出**旧名字：`dir(odoo.http)` 实测只剩 `Controller / Response / request / route` 四个旧 API + 子模块名（`dispatcher / geoip / requestlib / response / retrying / router / routing_map / server / server_log / session / stream`）。⇒ `from odoo.http import content_disposition` **ImportError**（装载期硬失败，看得见）；`http.serialize_exception(e)` **AttributeError**（只在异常分支里跑到，平时看不见） | 命中 2 处，都在 `tour_accounting/controllers/statement_report.py`（xlsx 报表下载控制器）：24 行 import、47 行 except 分支。20 的正解就是上游自己的写法（`addons/web/controllers/report.py:10` → `from odoo.http.dispatcher import serialize_exception`；`odoo/http/stream.py:34`）。**这两处不能回落到 19**（19 没有 `odoo.http.dispatcher`），与 #4/#11 那类双兼容修复不同，必须留在 20 分支。已在 `check_legacy_api.py` 加规则 `odoo.http 导出变更(19)`（内置 20 白名单，`from odoo.http import X` 与 `http.X` 两种写法都查）：19 生产树报 2、已适配树报 0 |
| 16 | 19 现网 `project_todo` = **uninstalled**，`project_task` 表 **0 行** | 20 的 `project_todo` 是 `'auto_install': True` 且只依赖 `project`（19 的 manifest 同标志，但现网当年没被拉起）⇒ 空库装 `project` 就连带装它，而它装机即给每个用户建一条 **`Welcome <用户名>!`** 任务（`project_todo/models/res_users.py:_generate_onboarding_todo`，两版都有这段代码） | **这条修正了本轮先前的一个误判**。之前把"`project_task.resource_type` 的 NOT NULL 没建上"判成非 delta（依据：两版字段定义逐字相同、19 库无该 SQL 约束、19 表 0 行）。真因是 20 装机时表里**已经有 1 行 null**：`tour_operation/models/project_task.py:19` 的 `resource_type` 是 `required=True` 的 Selection，NOT NULL 撞已有行 → 日志 `Missing not-null constraint on project.task.resource_type` ×2（12:12:26 那条 ERROR 同源）。后果评估：① 功能不破（ORM 仍在 create 时强制），但 **DB 层没有 NOT NULL**，裸 SQL/ETL 写 null 不会被拦 → 记进 B2 校验判据；② `tour.dashboard._get_pending_bookings()` 按 `resource_type` 分组，该 welcome 行 `state='01_in_progress'` 会以 `False` 组冒出来 → 分组要容忍 False（单测已按"缺项显式给 0"写死）；③ 切换后用户会看到"我的待办"菜单和一条欢迎任务，**属可见变更，要么业务确认，要么装完 `project_todo` 卸掉** |
| 17 | — | 空库装这 19 个 tour_*（+ `purchase`）连带引入 **12 个 19 现网没装的模块**：`project_todo`（见 #16）、`account_payment_custom`、`portal_discuss`、`base_address_extended`、`mysubscription`、`website_sale_project`、`account_qr_code_sepa`、`base_report_wkhtmltox`、`crm_mail_plugin`、`mail_plugin`、`project_mail_plugin`（后 6 个 + `mysubscription` 都是 20 的 `auto_install` 连锁） | 逐个都是"20 比 19 多出来的界面/数据面"，B3 切换前的模块清单比对必须以此为准：**目标不是"和 19 一模一样"，而是"差异都有名字"**。`account_payment_custom` / `portal_discuss` / `base_address_extended` 三个非 auto，说明是被真实 depends 链拉进来的，B1 收尾时要定位链条归属再决定收不收敛 |

结论：**"财务先做"是对的**——这一串里 5/6/7/9/10/11 都只有真跑单测才看得见，静态 diff（§5.4）看不见，
它们分别落在 ETL 判据、权限决定和报表可用性上，越晚发现越贵。
第二批（#12/#13）进一步说明：**只测财务不够**。#13 是"静默数错"型，18 处分散在门户看板和 dashboard 计算字段里，
单测只覆盖了其中 4 处，其余靠静态检查器全仓扫；#12 则把"19 测试为什么能过"这个隐含前提
（生产库里 admin 的手工组关系）暴露成一条 **B2 迁移数据规则**。
#14 是这条规则的第二次独立命中：产品/项目创建权限同样靠手工组，且**必须落成签字决定**，不能只当测试夹具问题改掉。

#15/#16 则是"空库全模块 `-i`"这一步（§5.7）才浮出来的：前者是 20 把 `odoo/http.py` 拆包后的导出收缩
（半硬半隐：import 炸在装载期、`http.X` 炸在异常分支），后者推翻了我自己对一条 ERROR 的"非 delta"判定——
两版代码逐字相同并不代表行为相同，**装机时表里已经有什么行**才是差异。
#17 是它的副产物：目标库比 19 多 12 个模块，B3 的比对基准因此不能是"和 19 一致"，只能是"差异都有名字"。

### 5.7 Gate B1 空库全模块 `-i` 实录（2026-09-22，基线 20.1a1）

判据（计划 §7）：**20 空库 `-i` 全绿 + 单测通过**。两次独立全装，结论一致：

| 项 | `b1gate3`（纯装载） | `b1gate4`（装载 + 单测，权威） |
|---|---|---|
| 命令 | 同上，去掉 `--test-enable` | 见下方"复现" |
| 安装模块数 | 121 | **125**（多出的 4 个来自 `purchase` 链） |
| tour_* 结果 | 19 装绿 / `tour_hr` 未装 | **19 installed / `tour_hr` uninstalled**（逐个已核对 `ir_module_module`） |
| 装载结论 | `odoo.modules.loading: Modules loaded.` | `Modules loaded.` ×2（装载 + 测试后重建 registry） |
| 单测 | — | **`0 failed, 0 error(s) of 129 tests`**（`--test-tags /tour_accounting,/tour_fleet,/tour_product,/tour_resource`） |
| ERROR | 1 条（#16 的 `Constraint not added: resource_type … null values`） | 5 条：1 条同源 + 4 条**断言型负例**（`duplicate key … tour_guide_uniq_guide_code`、`null value … tour_supplier.name` —— 唯一性/必填用例故意触发的 `sql_db: bad query`） |

复现（**端口与 addons-path 是指定值，不要改成 8069**）：

```bash
docker exec odoo20-db psql -U odoo -d postgres -c "CREATE DATABASE b1gate4 OWNER odoo TEMPLATE template0;"
cd /home/adai/odoo20 && PYTHONPATH=/tmp/b0/pylibs ./odoo-bin -c odoo.conf -d b1gate4 \
  --addons-path="odoo/addons,addons,/tmp/b0/b1addons" --http-port=28169 --no-http \
  --stop-after-init --without-demo \
  -i tour_base,tour_accounting,tour_budget,tour_cfo_portal,tour_cmo_portal,tour_coo_portal,\
tour_fleet,tour_guide_portal,tour_menu,tour_operation,tour_order,tour_pm_portal,tour_product,\
tour_report,tour_resource,tour_shopping,tour_tourist_portal,tour_website,tour_website_sale,purchase \
  --test-enable --test-tags /tour_accounting,/tour_fleet,/tour_product,/tour_resource
```

**唯一的 gate 阻塞项是 `tour_hr`**：它经 `hr_resignation / ohrms_loan / hr_reward_warning /
oh_employee_documents_expiry` 拉进 Webkul 链，装载期 `TypeError: Model 'hr.leave.type' does not
exist in registry`（F5）。19 个 tour_* 与它无 depends 关系，所以 gate 可以先于 payroll 范围决定通过。

WARNING 分类（125 模块全装一轮，共 17 类；逐类定性，不靠"看起来无害"）：

| 计数 | 内容 | 定性 |
|---|---|---|
| 32 | `tour.plan.account: inconsistent 'compute_sudo' / 'store' for computed fields` | **19 同源**（`odoo/orm/registry.py:557,574` 两版都有）→ 非 delta，是既有代码味道：同模型内 compute 字段的 `store`/`compute_sudo` 不一致。归 B1 收尾的清理清单，不阻塞 gate |
| 63 | `Translated stored related field (res.company.name / res.partner.commercial_company_name / project.task.partner_name / partner_company_name) will not be computed correctly` | **20 新增校验**（`odoo/orm/fields_textual.py:53`），但报的 4 个字段**全在上游自己的定义上**（19 的 `res.company.name` 同样是 `related='partner_id.name', store=True`），tour_* 无一重声明 → 接受为上游噪音，不动 core |
| 18 | `Index attribute on 'res.partner.name' ignored, only trigram index…` | 上游字段、19 同源（`registry.py:863` vs 19 `:557+`）→ 噪音 |
| 6 | `Model attribute '_sql_constraints' is no longer supported, please define models.Constraint` | **20 新弃用**：还能用（约束照样建），但要迁。tour_* 仅 3 个文件用到（`tour_accounting/models/account_period.py`、`tour_base/models/tour_bank_account.py`、`tour_fleet/models/fleet_vehicle.py`），而 `models.Constraint` 我们已在 `tour_accounting` 里用了 7 处 → 有现成范式，属**低风险收尾项**，且 `Constraint` 是 20-only，不能回落到 19。**已迁**：三个约束改为 `_uniq_code` / `_uniq_acc_number` / `_uniq_licence`，实测目标库里约束以新名字存在（`tour_account_period_uniq_code`、`tour_bank_account_uniq_acc_number`、`fleet_vehicle_uniq_licence`），旧名字已消失 → **行为等价、约束名变了**，B2 ETL 报错文本按新名字认 |
| 6 | `Two fields (plan_class, plan_category) of tour.plan() have the same label` | **已修**。实测两者不是同一件事：`plan_category` 是按业务模式自动归类的 Selection（现网 regular 59139 / fit 23372 / booking 4410 / independent 6），`plan_class` 是源系统原文 Char（散客 730 / 团队 33 / 购物 4 / 单订 1，其余 86157 行为空）→ 把 `plan_class` 的 label 改成「源系统分类」并加 help，**不动数据也不动 `plan_category`**。同样的 label 也出现在 `tour.plan.reg`，一并改 |
| 2 | `Two fields (note, dunning_id) of tour.dunning.action() have the same label: 催收记录` | **已修**：`dunning_id`（m2o 指向 `tour.dunning`）改叫「催收单」，`note` 保留「催收记录」 |
| 4 | `tour.plan.account.report_from_type: selection attribute will be ignored as the field is not a selection` | **已修**：该字段是 `related='plan_id.from_type'`，`selection=` 死属性（取值由被关系字段决定）→ 删列表，装/升两轮实测字段仍可选、无新 WARNING |
| 3 | `Field tour.account.period.state: unknown parameter 'tracking'` | **已修，且是 19 同源**：`tour.account.period` 不是 mail thread 模型，`tracking=True` 在两版都不生效（20 只是开始报 WARNING）→ 直接删参数。**不存在"丢了变更历史"的问题**（19 从来没有过） |
| 2 | `Missing not-null constraint on project.task.resource_type` | 见 #16，非 delta 但产生 B2 判据 |
| 3 | `Error-prone use of @class in view header_contact_info` | 19 同源（`ir_ui_view.py:416/430`）→ 既有 |
| 1 | `tour_website` 一处 RST docstring「Title underline too short」；1 处 `markdown is not installed` | 前者纯文档；后者 **19 容器同样没装 `markdown`** → 非 delta，但 20 的 mail 更多走 markdown 渲染，记进 `Dockerfile.odoo` 的 pin 待办（A0-5 同一处） |

**与 §7 计划的差异**：计划写的是"tour_* 21 个去掉 tour_saas"。实测口径是 **20 个 tour_ 前缀模块**（`tour_saas` 不在适配树内，`tour_hr` 被 F5 挡住），
且必须带上 `purchase` 才能覆盖 19 现网的模块面。这条差异本身要写进 B1 签字页。

**复测（§5.8 的门户修复之后）**：门户修复后又跑了**两次**全新库 ——
`b1gate5`（只含 §5.8 的模板/控制器修复）与 `b1gate6`（再加 §5.7 表里那 4 类 WARNING 的清理），
逐项与权威列相同：125 模块 / `Modules loaded.` / **`0 failed, 0 error(s) of 129 tests`** / `tour_hr` 仍未装
（日志 `/tmp/b0/gate_b1_5.log`、`/tmp/b0/gate_b1_6.log`）。
⇒ 这些修复**没有把装载面改坏**，这条是本节作为 gate 判据的自洽性检查；
B1 签字页引用 `gate_b1_6`（最新一次全装 + 单测），`gate_b1_4` 作为首次达成记录保留。

**控制器改完（#24/#25）之后的终审：`b1gate8`（权威）** —— 125 模块 / `Modules loaded.` ×2 /
**`0 failed, 0 error(s) of 129 tests`** / 无 CRITICAL（`gate_b1_7` 曾出现 1 条
`odoo.service.httpd … quitting` CRITICAL：冒烟服务器还占着 28169，装载与单测因 `--no-http` 未受影响，
但为了让权威日志干净直接弃跑重跑）。同一轮 `b1gate8` 上重跑门户 GET 冒烟：
**44×200 / 0 Traceback / 0 ERROR**，11 条非 200 全是 `id=1` 数据性 404 + 1 条正确 403 + 1 条 303，
六个门户页 `<title>` 均渲染自家标题（无一页落回 "No Access"）⇒ §5.8 的第三段判据在**含前端修复的最终树**上成立。
跑完已用 `scripts/migration/smoke/teardown_smoke_fixtures.py` 清空夹具
（`guides=[25] users=[smoke_bot_admin, smoke_bot_portal]` → `LEFT … =0`），gate 库里不留冒烟账号。


### 5.8 第三段判据：门户运行时冒烟（2026-09-22）+ 顺带查出的 19 现网潜伏缺陷

装载全绿 + 单测 0 失败，**仍不等于门户可用**：tour_* 的门户页面是 `type='http'` 的控制器 +
服务端 QWeb，单测里一条都没覆盖（19 现网总共只有 17 个单测）。所以在 `b1gate4` 上起 28169 服务，
登录一个真实账号，把 `tour_*/controllers/**` 里所有 GET 路由逐个 curl。

**方法论（否则必得假绿）**：① 20 的 `/web/login` POST **必须带 csrf_token**（从登录页抓），
否则 `login=400`、所有探针都落在匿名会话上；② 门户组的判定是
`group in request.env.user.group_ids`，**只认显式成员**（implied 组不算），所以测试账号要逐个
授予 5 个门户组；③ 导游门户靠 `tour.guide.partner_id == user.partner_id` 认身份，
没有这条记录时每个控制器都渲染自家 "No Access" 模板 —— **0 个 500 是假绿**。
首轮诚实结果：`15×200 / 29×500 / 50 个 Traceback`。

修完四类后：`44×200 / 0 traceback / 0 ERROR`；剩余非 200 全部是"探针用的 `id=1` 记录不存在"
（404，属数据）和 1 个 403（`/my/guide/dispatches/1` 越权保护，属**正确行为**）。

| # | 现象 | 实测证据 | 定性与处置 |
|---|---|---|---|
| 18 | `/my/{cfo,coo,guide,tourist}/*` 列表页 500：`QWebError: SyntaxError: t-call must be on a <t> element (actually on <div>)` | 抛点在 19 `ir_qweb.py:2550` 与 20 `:2658`，**两版逐字相同**；源码树里 `<div t-call="portal.pager"/>` **14 处**（tour_guide 4 / tour_coo 4 / tour_cfo 3 / tour_tourist 3）。**19 现网实测**：`odoo shell -d tms` 里 `env['ir.qweb']._render(生产 view id)` → 同样 `SyntaxError`，命中 14 个生产视图（4208/4210/4211、4223/4224/4225/4226、4196/4198/4200/4202、4231/4233/4235） | **不是 19→20 delta，是 19 现网今天就坏的潜伏缺陷**：这些门户列表页一旦渲染就 500。⇒ 已改 `<t t-call>`（双兼容，可原样回落 19），并给 `check_legacy_api.py` 加规则（正则要求 `<tag` 与 `t-call=` 之间无引号，避开 `<xpath expr="//t[@t-call=…]">` 误报）。19 树报 14、适配树报 0。**这类缺陷列级 diff、装载、单测三层都看不见，只有渲染看得见** |
| 19 | `/my/guide/expenses/new` 500：`KeyError: 'context_today'`（编译后的模板行里抛，view 2694 = `tour_guide_portal.portal_expense_new`） | 服务端 QWeb 的注入名单 19 `ir_qweb.py:1303-1327` / 20 `:1373-1397` **两版都没有 `context_today`**（有 `time/datetime/relativedelta/json/env/user_id/…`）；`context_today` 只出现在 `tools/view_validation.py:27` 的**客户端表达式白名单**里 | 同类 **19 潜伏缺陷**。修法分面：`t-att-*` 表达式里 → 改 `datetime.date.today()`；后端表单 `domain="[('x','=',context_today()…)]"` → **合法不动**（Webkul `oh_employee_documents_expiry` 那 3 处一度被我批量替换掉，已回退）。规则判据因此只用 `t-att-` 前缀 |
| 20 | `/my/cfo/{expenses,commissions,loans}` 500：`KeyError: 'limit'` | 真符号是 `portal.controllers.portal.pager`（**没有 `portal_pager` 这个东西**），其返回字典 19/20 都只有 `page_count/offset/page/page_first/page_previous/page_next/page_last`，**无 `limit`**；同仓其余门户模块本来就写 `pager['offset'] + 20` | 同类 **19 潜伏缺陷**，3 处已改成 `+ 20`；`check_legacy_api.py` 加 `pager['limit']` 规则（不可机械替换，页长是调用方自己传的 `step=`） |
| 21 | `/my/coo`、`/my/coo/dispatches` 500：`TypeError: PortalGuide._get_dispatch_domain() missing 1 required positional argument: 'guide'` —— 调用点在**另一个模块** `tour_coo_portal/controllers/portal.py:73` | 20 的 `routing_map.py:268-279` 与 19 的 `http.py:887-899` 的 `build_controllers()` **逐字相同**：所有从 `CustomerPortal` 派生的控制器被 `type(name, tuple(reversed(leaf_controllers)), {})` **合并成一个类**。于是 `tour_guide_portal.PortalGuide._get_dispatch_domain(self, guide)` 遮蔽了 `tour_coo_portal.PortalCOO._get_dispatch_domain(self)` | **架构事实，两版一致**（19 同样会中，只是没人访问 `/my/coo`）。规则：门户控制器的私有 helper **必须带模块前缀**（已把 COO 侧改名 `_get_coo_dispatch_domain`）。顺手做了跨模块重名扫描（AST，`tour_*/controllers/*.py`）：修完只剩 `_int`（两模块各自私有）和 `_prepare_home_portal_values`（靠 `super()` 链，是设计用法）→ 这条扫描要进 B1 收尾清单 |
| 22 | `/tours`（官网线路列表）500：`ValueError: Cannot convert product.category.complete_name to SQL because it is not stored` | 19：`complete_name = …, store=True, recursive=True` + `_order = 'complete_name'`；20：`compute=…, search='_search_complete_name', recursive=True`，**没有 `store=True`**，`_order` 改成 `'parent_id desc, name asc'`（`product/models/product_category.py`）。列还在，**所以 §5.4 的列级 diff 完全看不见** | 真 19→20 delta，且只在运行时暴露。已删掉控制器里的 `order='complete_name'`，交给模型默认 `_order`（两版都能排出可接受的顺序）。⇒ 加进 B2 规则：**任何 `order=`／裸 SQL 都不能引用下面这 15 个字段** |
| 23 | — | 由 #22 造出第二台"列级 diff 之外的探测器"：比对两侧 `ir_model_fields.store`（19 现网 vs 20 空库），取"字段仍在 20 存在但 store 由 true→false"，再排除 o2m/m2m 与噪音 | **15 个真业务字段翻成非存储**：`product.category.complete_name`、`res.company.expense_account_id`、`res.company.income_account_id`、`res.partner.global_location_number`、`account.report.active`、`hr.resume.line.department_id`、`hr.version.departure_date/departure_description/departure_reason_id`、`iap.account.balance`、`product.pricelist.item.price_markup`、`res.device.browser/device_type/platform`、`website.menu.url`。前三个直接命中我们的报表 SQL 与按公司筛科目的写法 → 写进 §8 的 B2 判据（ETL 侧同理：这些列不在表上，`INSERT/SELECT` 带它们必错） |

| 24 | `/shop/tour/add` POST 500：`AttributeError: 'Request' object has no attribute 'website'`（`tour_website_sale/controllers/main.py:30`） | 19 在 `website/models/ir_http.py:265` 赋 `request.website = …`；20 全树没有这个赋值，改由 Environment 提供同名属性（`odoo/orm/environments.py:303`：`self['website'].browse(context['website_id'])`）。实测 19 的 Environment **没有** `website` 属性 | 真 19→20 delta，已改 `request.env.website._create_cart()`；**这条不能回落到 19**。同时把整棵适配树里用到的 `request.*` 名字**穷举比对**了一遍：只有 10 个（`cart/env/httprequest/session/render/redirect/not_found/make_response/geoip/website`），除 `website` 外 20 都还在（`cart` 由 20 的 `website_sale/models/ir_http.py:25` 继续挂）。`check_legacy_api.py` 加 `request.website` 规则（19 树 1 处、适配树 0 处） |
| 25 | 「未选班期」和「人数全 0」两种非法提交**返回 303 加购成功**，购物车里静默多出一行 `departure_id = NULL`、单价 = 商品模板 `list_price` 的线路产品（实测留在 `b1shop1` 的 order 4 / line 4） | 判据不在 20 里变：`_prepare_order_line_values` 对 `departure_id` 为空是"当普通产品行放行"（普通商品要走同一个 `_inherit`），而 `quantity=0` 在 20 的 `_cart_update` 里是删行/无操作，两条路都**不进** `_validate_tour_booking`。⇒ GET 冒烟和"正向一条链路"永远看不见 | **两版同源的校验洞**（19 现网同样能提交），已在**控制器侧**补前置判据（缺班期 / 人数 ≤0 → `?tour_error=`），并抽出 `_tour_booking_error` helper（按 #21 的规则带模块前缀）。4 条负例现在全部落到正确提示、正例合计不变。**教训写进判据**：门户/电商冒烟必须带负例，"没有 500"不等于"校验在工作" |

**这批"只有渲染才看得见"的缺陷有三条（#18/#19/#20）在 19 现网同样是坏的**，
所以修法都选了两版等价写法（`<t t-call>`／`datetime.date.today()`／`+ 20`），**可以原样回落到 19 分支**，
不必等 B3；回落与否是业务决定（见 §12 的待签字清单），但它们今天的 500 是真的。

**同一轮还顺手清掉了 §5.7 表里的 4 类 WARNING**（都在 `-u` + 全新库 `-i` 两轮实测归零）：
字段同名 label（`plan_class`→「源系统分类」，实测它与 `plan_category` 本来就不是同一件事：
现网 `plan_class` 只有 散客730/团队33/购物4/单订1，其余 86157 行为空，而 `plan_category` 是自动归类的
regular/fit/booking/independent）、`dunning_id`→「催收单」、`report_from_type` 的死 `selection=`、
`tour.account.period.state` 的死 `tracking=`（**该模型没有 mail thread，两版都不生效**，
所以"删参数"不丢功能）、`_sql_constraints` → `models.Constraint` ×3
（**约束名随属性名变**：`tour_account_period_uniq_code` / `tour_bank_account_uniq_acc_number` /
`fleet_vehicle_uniq_licence`，旧的 `code_unique`/`acc_number_uniq`/`unique_licence` 已不在库里
→ B2 ETL 撞唯一键时的报错文本按新名字认）。
门户 `<title>` 露 xmlid 的根因也查明：**`tour_guide_portal` 的 12 个模板从来没写 `name=`**，
`ir_ui_view.name` 因此回落成 xmlid（19 生产库里实测同样是 `portal_guide_home`，**非 delta**）→ 补中文名。
清理后重跑全新库 `b1gate6`：**125 模块 / `Modules loaded.` / `0 failed, 0 error(s) of 129 tests`**，
剩余 WARNING 全是 §5.7 定性过的"上游同源噪音 + `compute_sudo` 代码味道"两类。

**判据还差第四段：前端 JS（20 删了 `web.public.widget`，2026-09-22 补做）**。门户冒烟只看
HTTP 状态码，而前端坏掉**不影响状态码**（JS 不被 Python import，页面照样 200）。分三步做：

1. **静态扫**：给 `check_legacy_api.py` 加第三个分支（`.py` → 服务端 `.xml` → `static/src/**/*.js`），
   规则 `web.public.widget`/`publicWidget`、`odoo.define(`、`$.fn.`；扫描前剥 `//` 行注释
   （`://` 不算注释），否则移植说明自己会被报成命中。实测：**两版树各 30 个前端 JS 文件**，
   19 生产树命中 3 处（全在 `tour_website_sale/static/src/js/tour_website_sale.js`），适配树 0 处。
2. **真渲染**：克隆 `b1gate6` → `b1shop1`（**gate 证据库保持原样不动**），用 `odoo-bin shell`
   造夹具（线路产品 + 已发布班期五档价）。踩到一条：**20 的 `shell` 从 stdin 跑脚本默认回滚**，
   不加 `env.cr.commit()` 会得到"脚本自己都打印成功了、库里却没有"的幻影。
   然后 GET `/shop/<slug>` → 200，且 DOM 契约逐项对上：`#tour_booking_wrap`、
   5 个 `name="{adult,child,old_man,student,baby}_num"` 的 `.tour_count`、
   `option[data-prices]`（jsonb 转义后浏览器解回合法 JSON）、`#tour_total_preview`；
   再到 `web.assets_frontend_lazy.min.js` 里确认**重写后的模块确实被打包进去了**
   （含 `PRICE_KEYS`/`tour_booking_wrap`，不含 `publicWidget`）。
   三边命名一致性也核了：模板 `name` ↔ JS 去 `_num` 后的 key ↔ `get_online_prices()` 的 key
   ↔ 服务端 `TOUR_COUNT_FIELDS`，四者同一套五档名。
3. **计算与接线**：`/tmp/b0/js_harness.mjs` 用最小 DOM 桩（`querySelector(All)`/`dataset`/
   `addEventListener`/`fire`）在 node 里**跑真实文件**，7 个断言全过：初次 refresh、
   `input` 改人数重算、`change` 切班期重算、档位**按 name 不按位置**（乱序 + 未知档 + 非数字）、
   未选班期显示 `—` 而不是 `NaN`、`data-prices` 坏 JSON 不抛、缺元素静默返回。
   这条正是打 19 版"靠 `.tour_count` 的位置对 `KEYS[i]`"那个静默算错钱的耦合。
4. **加购闭环**：`/tmp/b0/shop_add_smoke.py`（带 csrf + 保持 cookie）POST 2/1/0/0/3 →
   `/shop/cart` 显示 **3,310.00**，与前端预览算法**逐分一致**；库里落
   `departure_id=8 / product_uom_qty=6 / 五档人数分列`。这一步当场抓出 #24 的 500。
   **仍未做的**：真浏览器里点一次（OWL 之外的执行时序、`type="module"` 的加载顺序）——
   桩件能证明"逻辑对、监听接上了"，不能证明"浏览器引擎里也这样"。这项挂在 B1 签字页的
   已知残留里，不假装已验。


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
