# 19 → 20 权限层迁移工具（B1 前置原型）

Odoo 20 删掉了 `ir.model.access` 与 `ir.rule` 两张表和两个模型，合并成单一模型
`ir.access`（`odoo/addons/base/models/ir_access.py`），安全文件也换成
`security/ir.access.csv`，列为：

```
id,name,model_id,group_id/id,operation,domain
```

`operation` 是 `crud` 的任意子集字符串（`r` / `ru` / `crud` …），`domain` 直接写在授权行里。
20 的判定语义（`_get_failed_accesses`）：

* **带 group 的行 = 授权（permission），彼此 OR**；
* **不带 group 的行 = 全局限制（restriction），彼此 AND**。

所以 19 的"先授权、再用记录规则收窄"**不能逐文件机械翻译**：只要同 (模型, 组) 还留着
一条无 domain 的宽授权行，把记录规则另写成一行就等于**没有收窄**（OR 掉了），
权限被静默放大。转换必须先把宽行拆掉、再把被规则覆盖的操作挂上 domain。

## 用法

```bash
D=/tmp/b1sec                                  # 工作目录
# 1) 从 19 现网导出权威权限现状（只读查询，走容器内 trust 认证，不在本机放口令）
docker exec tms-db psql -U odoo -d tms -qAt -c "copy (
  select coalesce(ad.module||'.','')||ad.name xid, a.name, m.model,
    coalesce(ag.module||'.','')||ag.name group_xid,
    a.perm_read, a.perm_write, a.perm_create, a.perm_unlink, a.active
  from ir_model_access a join ir_model m on m.id=a.model_id
  left join ir_model_data ad on ad.model='ir.model.access' and ad.res_id=a.id
  left join res_groups g on g.id=a.group_id
  left join ir_model_data ag on ag.model='res.groups' and ag.res_id=a.group_id
  order by m.model) to stdout with (format csv, header true)" > $D/acc19.csv

docker exec tms-db psql -U odoo -d tms -qAt -c "copy (
  select coalesce(d.module||'.','')||d.name xid, r.name, m.model,
    coalesce(r.domain_force,'') domain, r.global,
    r.perm_read, r.perm_write, r.perm_create, r.perm_unlink, r.active,
    coalesce((select string_agg(coalesce(gd.module||'.','')||gd.name, ',')
              from rule_group_rel rg join res_groups gg on gg.id=rg.group_id
              left join ir_model_data gd on gd.model='res.groups' and gd.res_id=gg.id
              where rg.rule_group_id=r.id),'') groups
  from ir_rule r join ir_model m on m.id=r.model_id
  left join ir_model_data d on d.model='ir.rule' and d.res_id=r.id
  order by r.id) to stdout with (format csv, header true)" > $D/rule19.csv

# 另需 model_xid.psv：`ir_model_data(model='ir.model') × ir_model.model`，用于 xmlid→模型名

# 2) 生成
python3 conv_security2.py $D <odoo20>/addons,<odoo20>/odoo/addons $D/out2
# 3) 落到 addons 副本（**绝不在生产 addons 上跑**）
python3 apply_security.py $ADDONS_COPY $D/out2
```

## 输出与实测（2026-09-21，alpha 基线 20.1a1）

| 项 | 数量 | 说明 |
|---|---|---|
| 19 权限现状 | 1,405 access 行 / 431 rule 行（119 全局，8 行无 XMLID，31 行无组） | 单公司 |
| 20 core 已声明 (模型,组) | 2,429 对 | 用于做差 |
| 生成 ir.access 行（v2 逐条平移） | **696** | grant_gap 283 / rule 264 / wide_custom_group 125 / global_restriction 22 / rule_only 2 |
| 桥接模块 | `tour_security_bridge`，522 行，depends 66 | 承载"官方组"的差量授权与全局限制 |
| **v3 有效权限重建**（`classify_rules.py` + `domains20.py`） | permission 1,407 行 + restriction 117 行 / 626 模型 | 待复核 **14**（NO_GRANT_POP 12、CTX_OUT_OF_20 2）；出站 domain 引擎自检 **0 条不可解析** |

### v2 的语义错误与 v3 的修正（必读）

v2 逐条平移时把「记录规则挂在**没有 access 行**的组上」判为 `ORPHAN_RULE`/`INERT_RULE` 丢弃，
共 77 条。**这是错的，且两个方向都会出错**：

1. 19 的组成员关系是继承的（`res_groups_implied_rel`：gid=本组、hid=被隐含的父组）。
   `sales_team.group_sale_salesman_all_leads ⇒ group_sale_salesman ⇒ base.group_user`，
   所以子组成员天然命中**父组**的 access 行 —— 规则不需要该组自己有授予。
2. 19 的记录规则按「用户所属的任意组」匹配，规则之间 **OR**、全局规则 **AND**，
   且"没有任何非全局规则命中该用户"时**不设限**。

于是 `crm.lead` 的 "All Leads"（挂 all_leads）是生效的：它把父组 salesman 的
"Personal Leads" 限制放宽回全部。v2 丢弃它 = 静默收窄（业务回归）；
把它当 restriction 平移 = 静默放宽（越权）。

v3 因此不再逐条平移，而是**按人群重建有效权限**：

* 人群 P（每个组一次）在模型 M 上的 ops = P 及其全部父组的 access 行并集（+ 无组行）；
* 有效域 = `AND(全局规则) ∧ OR(命中 P 的组规则)`；组规则命中恒真域（`[(1,'=',1)]`）
  视为"该人群不受组规则限制"；
* 落成两种 20 行，语义一一对应、无需人工合并：**全局规则 → 无 group 的 restriction 行**
  （20 里 restriction 彼此 AND，与 19 完全一致），**组规则 → 带 group 的 permission 行 + domain**
  （20 里 permission 彼此 OR，与 19 组规则 OR 一致）。

用法（输入仍是 §用法 1) 导出的三个 CSV，另需 `group_xid.csv`）：

```bash
# 组继承关系导出（19 现网，只读）
docker exec tms-db psql -U odoo -d tms -c "COPY (
with gx as (select d.res_id id, min(d.module||'.'||d.name) xid from ir_model_data d
            where d.model='res.groups' group by d.res_id)
select g.id, gx.xid, coalesce(string_agg(pp.xid,'|' order by pp.xid),'') parents
from res_groups g join gx on gx.id=g.id
left join res_groups_implied_rel rel on rel.gid=g.id
left join gx pp on pp.id=rel.hid
group by g.id, gx.xid) TO STDOUT WITH (FORMAT csv, HEADER true)" > group_xid.csv   # 106 组
```

多条组规则命中同一人群时的 domain 合并**不手写**：`domains20.py` 直接调用 20 自己的
`odoo.orm.domains.Domain`（纯 AST 工具，离线可用、不需要 DB）做 `a | b`，再用 `list()`
展平回正确 arity 的前缀记法。19 域里的 `user.id`/`company_ids + [False]`/`time.strftime(...)`
由 `Tok` 哨兵保留结构、`repr()` 原样吐回。实测 35 条多规则人群全部自动合并成功。

出站还有一道硬校验：20 的 access domain 可求值上下文**只有** `user / time / company_id / company_ids`
（`odoo/addons/base/models/ir_access.py:312 _eval_context`）。工具对每条出站 domain 扫自由符号，
超出即记 `CTX_OUT_OF_20`（实测 2 条，都是 core 的 `website` 多站点 pricelist 规则）。
这类域落库后 `safe_eval` 会 NameError（**报错而非默默放行**），但必须在 B1 显式改写。

```bash
# 必须用 odoo20 的解释器 + PYTHONPATH，才能借它的 domain 引擎
cd <本目录> && PYTHONPATH=/home/adai/odoo20:. SEC20=/tmp/b0/sec20 \
  /home/adai/odoo20/.venv/bin/python classify_rules.py --outdir $SEC20/eff
# → eff/rows_effective.csv（model,group,ops,domain,source）1,402 行
#   eff/restrictions_effective.csv（model,ops,domain,source）117 行
#   eff/review.csv（NO_GRANT_POP 12 + CTX_OUT_OF_20 2）
# 本次实测的三份产物已随工具留档在 ./eff/（136 KB，只含模型名/组 xmlid/domain，无业务数据）
```

未带 `PYTHONPATH=/home/adai/odoo20` 时工具会**退化**为不合并（多规则人群进 NEEDS_DOMAIN_MERGE
人工队列），并打印 `MERGE=False` —— 不会静默生成一条拼错的域。

## 导出数据的两处方向陷阱（改脚本前必读）

1. **组继承的方向**：`res_groups_implied_rel` 的列名反直觉 —— `res_groups.py:75` 定义
   `implied_ids = Many2many('res.groups', 'res_groups_implied_rel', 'gid', 'hid')`，
   即 **gid = 本组、hid = 被隐含的父组**（成员自动属于父组）。按名字猜会把它读反，
   读反后所有人群的授予都会算少，产出一批假的 NO_GRANT_POP。
   导出必须用 `left join res_groups_implied_rel rel on rel.gid = g.id` + `pp.id = rel.hid`。
2. **一条规则可挂多个组**：19 现网有 25 条规则的组列表是逗号分隔（如
   `base.group_portal,base.group_public`）。20 的 `ir.access` 只有单个 `group_id`，
   故按组拆成多行同 domain 的 permission 行（20 里 permission 彼此 OR，语义等价）。

## 复核队列只有 14 项

12 条 `NO_GRANT_POP`（该人群整条继承链上没有任何 access 行 → 规则在 19 里本就是死的）
+ 2 条 `CTX_OUT_OF_20`（core 的 website 多站点 pricelist 域用到 20 不提供的 `website` 符号）。
其中真正需要业务签字的只有 3 条：

| 模型 | 人群 | 实测事实 | 20 侧建议 |
|---|---|---|---|
| `hr.leave` / `hr.leave.allocation` | `hr_holidays.group_hr_holidays_responsible` | 19 里该组只有规则、没有任何 CRUD 授予；**该组现网 0 个活跃用户** → 规则确实无从生效 | 可直接丢弃并记录；若日后启用「假勤负责人」审批，需同时补授予 + domain |
| `tour.guide.loan` | `base.group_user`（89 活跃用户） | 自有 `tour_accounting.rule_tour_guide_loan_self` 挂在 `base.group_user`，但该模型只授予 portal(0 人)/cfo(1 人)/finance/manager 四组 → **这条"只看自己"的规则从未生效过** | 改挂到实际持有授予的组（多半是 finance/manager 想限自己），并在 B1 加一条访问单测；不改就是延续现网的既有行为 |

## 已知边界（不要当成成品）


1. `grant_gap` 是**复核清单**，不是自动补权限：20 core 只保留了 19 里 61%（687/1131）的
   官方 access XMLID，其余是官方主动改小或改名。无脑回填会把官方收紧的权限再放开。
2. 模型名解析依赖 19 现网 `ir_model`，20 里被删的模型（`res.bank`、`hr.leave.type` 等）
   会产生悬空行，需要按 TDS-30 §4/§5 的处置结论先清理。
3. 无组授权行（19 里 31 条，如匿名可读）在 20 没有等价写法 —— 无组行是"限制"不是"授权"，
   必须显式改成 `base.group_public` / `base.group_portal`，逐条签字。
   v3 的 `NO_GRANT_POP`（32 条）与这类同源，都属"20 无等价载体"。
4. `noupdate` 标记、`ir.access` 的 `is_standard` 归属、以及"改上游行"只能通过在自己模块里
   复用同一 XMLID 覆盖实现 —— 这条尚未在原型中处理。
5. 视图层的 `t-esc`/`t-raw`（现网 560 处 / 23 文件）不属于本工具范围，见 TDS-30 §5.2。
6. v3 只重建**数据可见性**，不覆盖 20 新引入的 `ir.access` 计算字段口径（`for_read/write/…`），
   落库前需在 20 空库对 `rows_effective.csv` 抽样做 `read` 权限矩阵回归（A1 报告的 §5 矩阵）。
