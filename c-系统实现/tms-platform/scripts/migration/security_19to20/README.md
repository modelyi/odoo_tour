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
| 桥接模块 | `tour_security_bridge`，522 行，depends 66 | **v2 产物已作废**：depends 含装不上的 `tour_accounting`/`hr_custody`，这份永远装不起来，仅留作对照 |
| **v3 有效权限重建**（`classify_rules.py` + `domains20.py`） | permission 1,407 行 + restriction 117 行 / 626 模型 | 待复核 **14**（NO_GRANT_POP 12、CTX_OUT_OF_20 2）；出站 domain 引擎自检 **0 条不可解析**；**已在真实 20 registry 装载 + 行为验证**（见「装载与行为验证」） |

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
# → eff/rows_effective.csv（model,group,ops,domain,source）1,407 行
#   eff/restrictions_effective.csv（model,ops,domain,source）117 行
#   eff/review.csv（NO_GRANT_POP 12 + CTX_OUT_OF_20 2）
# 本次实测的三份产物已随工具留档在 ./eff/（136 KB，只含模型名/组 xmlid/domain，无业务数据）
```

未带 `PYTHONPATH=/home/adai/odoo20` 时工具会**退化**为不合并（多规则人群进 NEEDS_DOMAIN_MERGE
人工队列），并打印 `MERGE=False` —— 不会静默生成一条拼错的域。

```bash
# 4) 装载 + 行为验证（scratch 库，勿在生产 addons/库上跑）
#    三道门一起给：模型注册表 / 组 xmlid / 已装模块，产物即"目标库现在能装的那一份"
#    另需 20 侧 model→module 归属表（默认读 $SEC20/model_owner20.psv）：
docker exec <20-ref-db> psql -U odoo -d <refdb> -c "COPY (
select m.model||'|'||coalesce(min(d.module) filter (where d.name like 'model\_%'), min(d.module))
from ir_model m join ir_model_data d on d.res_id=m.id and d.model='ir.model'
group by m.model) TO STDOUT" > model_owner20.psv
#   注意 20 里 ir_model_data.model 存的是**完整技术名** 'ir.model'（不是 'model'），写错查不出行
docker exec <20-db> psql -U odoo -d <db> -tAc "select model from ir_model"       > models.txt
docker exec <20-db> psql -U odoo -d <db> -tAc \
  "select d.module||'.'||d.name from ir_model_data d where d.model='res.groups'" > groups.txt
docker exec <20-db> psql -U odoo -d <db> -tAc \
  "select name from ir_module_module where state='installed'"                    > installed.txt
python3 gen_ir_access.py --eff $SEC20/eff --scope-modules <...> --also-custom-groups <...> \
  --target-models models.txt --target-groups groups.txt --installed-modules installed.txt \
  --out ir.access.<scope>.csv --manifest-out <addons>/tour_security_bridge/__manifest__.py
#   → ir.access.<scope>.csv 拷进 <addons>/tour_security_bridge/security/ir.access.csv
#   → odoo-bin -i tour_security_bridge（--without-demo 不要再写 =all）
#   → odoo-bin shell … < probe_bridge.py   打印可见性矩阵；shell 退出即回滚，不留测试数据
```

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

## 装载与行为验证（实测 2026-09-21，alpha 20.1a1，scratch 库 `b1sec7`）

把 v3 产物真的装进 20 registry 跑了一遍 —— **这一步抓到了一个会整批失败的真实缺陷**：

* `operation` 不是任意子串，而是 20 的 `Selection`（`ir_access.py:16` 的 15 个键），
  键内顺序固定为 **`crud`**。v3 早期按 19 的 `perm_read/write/create/unlink` 顺序拼出
  `rucd`/`ruc`/`rc`/`ucd`，这些值不在 Selection 里 → 被写成 NULL →
  `null value in column "operation" violates not-null constraint`，**1,524 行里 959 行装载失败**。
  只查 CSV 文本永远看不出这个问题（`rucd` 看起来完全合法）。
  已修：`canon_ops()` 统一按 `crud` 排序 + 两个脚本出站时无条件硬校验非法值即失败。
  修复后 permission/restriction 的 ops 分布为
  `crud 646+112 / r 526+1 / cru 185+1 / ru 32+2 / cr 13 / cud 2 / rud 5 / cu 1`，非法值 0。
* 装载实测：作用域裁剪后 188 行 → `security/ir.access.csv` →
  `-i tour_sec_bridge3` **0 ERROR**，`select count(*)=188`、带 domain 40 行全部落库。
* 行为实测（`probe_bridge.py`，shell 事务结束自动回滚，不留测试数据）：

  | 探针 | 总数 | 目标用户可见 | 判据 |
  |---|---|---|---|
  | `tour.guide` / portal（domain = `partner_id = user.partner_id.id`） | 2 | **1** | ✅ domain 生效 |
  | `tour.guide` / superuser（对照组） | 2 | 2 | ✅ 排除"数据没建出来"的假阳性 |
  | `res.partner.bank` / internal（domain = `partner_id.employee_ids = False`） | 2 | **1** | ✅ **带点的关系路径 domain 在 20 可用** |
  | portal 用户 `read()` 域外记录 | — | `AccessError` | ✅ 引擎侧记日志 `Access Denied ... model: tour.guide` |
  | portal 用户 `read()` 域内记录 | — | OK | ✅ 没有过度收窄 |

顺带抓到的 20 侧字段/API 事实（已并入 TDS-30 §7）：`res.users.groups_id` → **`group_ids`**
（新增 `all_group_ids` 传递闭包、`base.group_user_regular` 新组；`res_groups_users_rel` 关系表未变
→ 象限 3 直拷 SQL 仍成立）；`res.partner.bank` 列改名 `acc_number→account_number`、
`sanitized_acc_number→sanitized_account_number`、`acc_holder_name→holder_name`，
`bank_id`/`currency_id` 消失、改为内联地址列；`--without-demo=all` 自 19 起是非法布尔值。

### 第二轮：整条生成链自动装载（同一天）

把手工裁剪换成 `gen_ir_access.py` 的自动作用域/依赖后，又抓到一条**方法级**事实：

* **`model → module` 的归属推断不足以判定"这行装得上"**。第一版自动 depends 用
  「20 参考库归属，查无则回落 19 归属」，结果 178 行里有 7 行装载失败
  （`null value in column "model_id" violates not-null`）—— 涉及
  `hr.contract.type` / `hr.version.wizard` / `applicant.send.mail` / `hr.expense.post.wizard`：
  19 把这些模型的 XMLID 记在 `hr`/`hr_expense` 名下，20 里要么模块独立（`hr_contract`）、
  要么向导已删，于是"依赖已装"的判断是假的。
* → 判据换成**目标库实际的 `ir_model` 注册表**（`--target-models`，取自
  `psql -tAc "select model from ir_model"`）。不在注册表里的行一律进
  `*.deferred.csv`（附原因，**不是丢弃**），依赖就位后重跑即回收。
* 复测：作用域内 307 行 → 172 行可装 + 135 行延后 → 自动 manifest（depends 21，全部真实存在）
  → `-i tour_sec_bridge5` **0 ERROR**、`count(*)=172`、带 domain 40 行。
  至此"导出 → 重建有效权限 → 裁剪 → 生成 manifest → 真实装载"整条链无需人工判读。
* 顺带修正 §用法 里那句"故意让它失败"：装载失败不再是设计意图，而是被 `--target-models`
  挡在前面的可预期延后。
* **第三道门是 same-day 补的**：只给 `--target-models`（不给 `--installed-modules`）时
  188 行"模型都存在"，但自动 depends 里出现 `tour_website_sale` —— 它在 20 侧还装不上
  （被 `res.bank`/OWL 卡住），于是 `-i tour_sec_bridge6` 直接 `Failed to load registry`。
  **这正是 v2 桥接模块（depends 66、含 `tour_accounting`）永远装不起来的原因**，
  现在被工具挡住了：`--installed-modules` 会把"依赖模块本身还没就位"的行也延后，
  三门齐用（models + groups + installed）产出的 172 行 = 已验证可装的那一份。
* 引用不存在的组 xmlid 同样会让整批 `ir.access.csv` 失败 → `--target-groups`。
  推荐用法：**三道门一起给**，产物与目标库状态一一对应，缺什么在 `.deferred.csv` 里看得见。

## 已知边界（不要当成成品）


1. `grant_gap` 是**复核清单**，不是自动补权限：20 core 只保留了 19 里 61%（687/1131）的
   官方 access XMLID，其余是官方主动改小或改名。无脑回填会把官方收紧的权限再放开。
2. 模型名解析依赖 19 现网 `ir_model`，20 里被删的模型（`res.bank`、`hr.leave.type` 等）
   会产生悬空行。**现已有机械判据**：`--target-models` 传目标库实际注册表，
   查无此模型即延后（见「第二轮」），不再需要靠 §4/§5 的清单人工比对。
3. 无组授权行（19 里 31 条，如匿名可读）在 20 没有等价写法 —— 无组行是"限制"不是"授权"，
   必须显式改成 `base.group_public` / `base.group_portal`，逐条签字。
   v3 的 `NO_GRANT_POP`（32 条）与这类同源，都属"20 无等价载体"。
4. `noupdate` 标记、`ir.access` 的 `is_standard` 归属、以及"改上游行"只能通过在自己模块里
   复用同一 XMLID 覆盖实现 —— 这条尚未在原型中处理。
5. 视图层的 `t-esc`/`t-raw`（现网 560 处 / 23 文件）不属于本工具范围，见 TDS-30 §5.2。
6. v3 只重建**数据可见性**，不覆盖 20 新引入的 `ir.access` 计算字段口径（`for_read/write/…`）。
   **装载 + 单点行为验证已做**（见上一节，含 domain 收窄与 AccessError 两个方向），
   但那只是合成数据；A1 报告 §5 的登录/权限矩阵在**迁移后的真实数据**上回归仍是必做项。
7. 桥接模块的 `depends` 已由 `--owner20` + 三道门自动算出（见「第二轮」），v2 手写的
   `tour_security_bridge`（depends 66、含装不上的 `tour_accounting`）已作废。
   仍待办的是**终局形态**：现网全模块就位后应只出一份 depends 完整的桥接层，
   而不是按库状态切多份；`.deferred.csv` 就是要随 B1 进度逐批回收的队列。
   另一个未处理项：`owner20` 参考库（`b0snap20`）只装了官方依赖闭包，
   它没有的模型会回落到 19 归属 —— 对 tour_* 自有模型正确，对"20 里换了归属的官方模型"
   会算错（本轮 7 行失败即此类），所以 `--target-models` 是**必需**而非可选。

## 规则域在 20 是装载期校验（`check_domains.py`，实测 2026-09-22）

19 的 `ir.rule.domain_force` 装载期**不求值**，写错的字段名可以躺平几年；20 的 `ir.access`
CSV 装载期就用真实 registry 求值域，一个坏域让**整批授权行装载失败**，表现是
`Invalid domain [...]: Invalid field tour.plan.reg.partner_id` 加一句
`Module loading tour_accounting failed`。本目录的 `check_domains.py` 做静态预检：

```bash
# 目标库字段目录（含 relation，用于点号跳）
docker exec odoo20-db psql -U odoo -d b1tour1 -AtF'|' -c \
  "select m.model, f.name, coalesce(f.relation,'') from ir_model_fields f join ir_model m on m.id=f.model_id" \
  > /tmp/b0/sec20/fields_b1tour1.psv
python3 check_domains.py <dir>/security/ir.access.csv --fields /tmp/b0/sec20/fields_b1tour1.psv [--split]
```

* 域用 `ast.parse(mode='eval')` + `ast.walk` 抽三元组，**从不 eval** 域文本。
* `--split` 把坏行隔离到 `<csv>.baddomains.csv`（先 `.bak`），好行留原文件，便于逐条定性。
* **判读**：坏域有两类，处置完全不同 ——
  (a) 字段在 20 真没了 → 删或改域；
  (b) 字段由**非依赖模块**追加（本轮：`tour.plan.reg.partner_id` 由 `tour_website` 加，
      而授权行在 `tour_accounting`）→ 装载期 registry 里没有它，必须把这一行移到
      "依赖两边"的桥接模块（本轮 scratch 里新建 `tour_sec_bridge7` 只装这一行）。
  这类不是死域，是**装载顺序问题**，所以 (b) 的成立前提是"该模块单独装"。
* **已知局限**：`--fields` 传的是**整库**字段目录，看不见"模块自身装载期还没有这个字段"的
  情况 —— 即上面 (b) 只能靠真跑 `-i` 才暴露，或人工看域里的模型是否出自非依赖模块。
  全库目录能查出的是 (a)。
