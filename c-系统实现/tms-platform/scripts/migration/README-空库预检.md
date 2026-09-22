# 空库装载预检三件套（B1 静态检查器）

## 为什么要这三个脚本

19 现网库是十几年 `-u` 增量演化出来的，很多**坏数据从来没被暴露过**：
前向引用（文件 A 引用的 xid 由后面才装载的文件 B 定义）、`ir.ui.menu` 只挂父不带
`name`、引用上游早已删除的字段/模型…… 这些在增量库里都能跑，因为记录早就存在了。
而 B1 的验收判据是**空库 `-i` 全绿**，上面每一个都会变成硬失败。

如果只靠"装一次报一个错、改一个再装一次"，每个缺陷一轮 1–3 分钟，且报错点往往离
真实原因很远（converter 会吞掉内层异常，要 `--log-handler odoo.tools.convert:DEBUG`
才看得见）。三个静态检查器把这件事从"逐个试错"变成"一次列全"：

| 脚本 | 检查什么 | 空库装载后果 |
|---|---|---|
| `check_xmlid_order.py` | xid 引用顺序 / 环 / 无 `name` 的 menu | `External ID not found`、`null value in column "name"` |
| `check_model_refs.py` | XML 里的模型名是否还存在 | `Model not found: xxx` |
| `check_field_refs.py` | XML `<field name>` 是否是真实字段 | `Invalid field 'xxx' in 'yyy'` |

三者都用 19 源码做过对照验证（对照组必须报出已知的真实缺陷，否则检查器不可信）。

## 用法

```bash
cd c-系统实现/tms-platform

# 1) 装载顺序 / XMLID。第二个参数是模块名（决定裸 xid 的归属前缀）
python3 scripts/migration/check_xmlid_order.py addons tour_accounting
#   → 报：前向引用、menu 缺 name、以及跨模块引用的处理建议
# --missing 会把"完全查不到定义的 xid"也升级为失败
python3 scripts/migration/check_xmlid_order.py /tmp/b0/b1addons tour_accounting --missing

# 2) 模型存在性：known = 导出 ir_model ∪ Python _name
docker exec odoo20-db psql -U odoo -d b1fresh -qAt \
  -c "select model from ir_model" > /tmp/b0/models20.txt
python3 scripts/migration/check_model_refs.py /tmp/b0/b1addons --known /tmp/b0/models20.txt

# 3) 字段存在性：必须用 ir_model_fields，不能用 information_schema
docker exec odoo20-db psql -U odoo -d b1fresh -qAt -c "
  select m.model || '.' || f.name from ir_model_field f join ir_model m on m.id=f.model_id" \
  > /tmp/b0/fields20.txt
python3 scripts/migration/check_field_refs.py /tmp/b0/b1addons --fields /tmp/b0/fields20.txt
```

## 已知判读要点

* **字段存在性的唯一权威是 `ir_model_fields`，不是数据库列**。
  `ir.actions.report.report_file`、`res.users.groups_id` 这类非存储/related 字段没有列，
  列级 diff 看不见它们（19→20 就漏掉了 `report_file`，19 有字段、20 没有）。
* **模型存在性同理**：只导出一部分库的 `ir_model` 会把"模块没装"误报成"模型没了"。
  所以要并上 20 源码全量 `_name`（`models20src_all.txt`），剩下才是真删除的模型。
* `check_xmlid_order.py` 的事件顺序里 `no_name` 必须排在自身 `def` 之前，否则
  "此前已定义"会把自己算进去，检查永远不触发（这个坑踩过一次）。
* 跨模块引用只报不计错：装载顺序由依赖图决定，真正会炸的是**同模块内**的前向引用。

## 实测到的缺陷数量（19 源码 → 20 空库）

* 装载顺序 / 无 name menu：25 处（tour_accounting），其中 14 处是仅用于改父级的
  `ir.ui.menu`，`name` 只能从 19 现网取回。
* 真被 20 删掉的模型：`account.group`（19 现网表 0 行）、`hr.leave.type`（Webkul 工资单）。
* 真被 20 删掉的字段：`ir.actions.report.report_file`（tour_accounting 19 处 / 5 文件）。
* 消失的核心 xid menu：`account.root_payment_menu`、`account.account_logs_menu`、
  `account_payment.*_menu`、`hr_expense.menu_hr_expense_account_employee_expenses`。
