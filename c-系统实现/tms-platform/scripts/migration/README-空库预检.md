# 空库装载预检：B1 静态检查器清单

## 为什么要这些脚本

19 现网库是十几年 `-u` 增量演化出来的，很多**坏数据从来没被暴露过**：
前向引用（文件 A 引用的 xid 由后面才装载的文件 B 定义）、`ir.ui.menu` 只挂父不带
`name`、引用上游早已删除的字段/模型…… 这些在增量库里都能跑，因为记录早就存在了。
而 B1 的验收判据是**空库 `-i` 全绿**，上面每一个都会变成硬失败。

如果只靠"装一次报一个错、改一个再装一次"，每个缺陷一轮 1–3 分钟，且报错点往往离
真实原因很远（converter 会吞掉内层异常，要 `--log-handler odoo.tools.convert:DEBUG`
才看得见）。这些静态检查器把这件事从"逐个试错"变成"一次列全"：

| 脚本 | 检查什么 | 空库装载后果 |
|---|---|---|
| `check_xmlid_order.py` | xid 引用顺序 / 环 / 无 `name` 的 menu | `External ID not found`、`null value in column "name"` |
| `check_model_refs.py` | XML 里的模型名是否还存在 | `Model not found: xxx` |
| `check_field_refs.py` | XML `<field name>` 是否是真实字段 | `Invalid field 'xxx' in 'yyy'` |
| `check_legacy_api.py` | Python 里 20 已删除的旧 API 写法（含 `odoo.http` 导出收缩）+ **服务端 QWeb 模板**的已删指令 + **前端 JS**（`static/src/**/*.js`）里 20 已删的注册表 | registry 建模期 `AttributeError`（连数据都装不到）／`ImportError` 装不上／模板内容静默不渲染／**JS 那一段装载和 HTTP 状态码都不报，只有浏览器控制台看得见** |
| `check_view_xpaths.py` | 视图继承的 `<xpath expr>` 锚点是否还在 | `Element '<xpath …>' cannot be located in parent view` |

`check_legacy_api.py` 里的 `read_group` 四条规则**不能按行匹配**（真实调用几乎都是跨行的），
单独走 `_scan_read_group`；对照实测：未改的 19 树命中 19 个调用点 + 47 处取值，
改完的 20 适配树 tour_* 归零。详见 TDS-30 §5.6 第 13 行。

`odoo.http` 规则（`_scan_http`）的判据是**运行时白名单**，不是猜的：20 把 `odoo/http.py` 拆成包，
`odoo/http/__init__.py` 只剩 21 行，`dir(odoo.http)` 实测只有 `Controller/Response/request/route`
四个旧 API 加子模块名。19 的 131 个公开名里 126 个取不到 → `from odoo.http import X` 当场
`ImportError`，`http.X` 则往往躲在 `except` 分支里（我们那处 `http.serialize_exception` 就是这样）。
两种写法都查。**这条改法不能回落到 19**（19 没有 `odoo.http.dispatcher`），所以它只属于 20 分支。

三个 XML 检查器在 `/tmp/b0/b1addons`（40 模块 / 299 个 XML）上跑出来 **0 命中**，
即 tour_* 的 XML 层已全清；剩余命中全在 Webkul（`hr.leave.type`、`report_file`）。

三者都用 19 源码做过对照验证（对照组必须报出已知的真实缺陷，否则检查器不可信）。

## 用法

```bash
cd c-系统实现/tms-platform

# 1) 装载顺序 / XMLID。第二个参数是模块名（决定裸 xid 的归属前缀）
python3 scripts/migration/check_xmlid_order.py addons tour_accounting
#   → 报：前向引用、menu 缺 name、以及跨模块引用的处理建议
# --missing 会把"完全查不到定义的 xid"也升级为失败
python3 scripts/migration/check_xmlid_order.py /tmp/b0/b1addons tour_accounting --missing

# 2) 模型存在性：第 2 个位置参数 = 目标库已有模型清单（位置参数，不是 --known）
docker exec odoo20-db psql -U odoo -d b1fresh -Atc "select model from ir_model" | sort -u > /tmp/b0/models20.txt
python3 scripts/migration/check_model_refs.py /tmp/b0/b1addons /tmp/b0/models20.txt

# 3) 字段存在性：必须用 ir_model_fields，不能用 information_schema
docker exec odoo20-db psql -U odoo -d b1fresh -Atc \
  "select model||'|'||name from ir_model_fields" | sort -u > /tmp/b0/fields20.txt
python3 scripts/migration/check_field_refs.py /tmp/b0/b1addons /tmp/b0/fields20.txt

# 4) 旧 API：只报"实测 19 有 / 20 无"的写法；--apply 只做零风险的 self._cr/_uid/_context 替换
python3 scripts/migration/check_legacy_api.py addons
python3 scripts/migration/check_legacy_api.py /tmp/b0/b1addons hr_custody hrms_dashboard --apply
# 5) 视图继承锚点：第 2 个参数 = 目标库名（脚本自己 docker exec psql）或事先导出的清单文件
/home/adai/odoo20/.venv/bin/python scripts/migration/check_view_xpaths.py /tmp/b0/b1addons b1tour1
/home/adai/odoo20/.venv/bin/python scripts/migration/check_view_xpaths.py /tmp/b0/b1addons b1tour1 tour_website --strict
#   需要 lxml，所以用 20 的解释器跑；默认只列候选（退出码 0），--strict 才把命中数当失败
# 6) 权限行的规则域（20 装载期就用真实 registry 求值，19 不校验）：见 security_19to20/check_domains.py
docker exec odoo20-db psql -U odoo -d b1tour1 -AtF'|' -c \
  "select m.model, f.name, coalesce(f.relation,'') from ir_model_fields f join ir_model m on m.id=f.model_id" \
  > /tmp/b0/sec20/fields_b1tour1.psv
python3 scripts/migration/security_19to20/check_domains.py \
  /tmp/b0/b1addons/tour_accounting/security/ir.access.csv --fields /tmp/b0/sec20/fields_b1tour1.psv --split
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
* `check_view_xpaths.py` **只能当排序清单，不能当判据**：它按 (priority, id) 重放继承来合成
  父视图 arch，但 Odoo 的合并 arch 还有没建模的环节（qweb `t-call` 展开等）。实测
  `//footer//a[contains(@href,'mailto:')]`（继承 `website.footer_custom`）被判定位不到，
  而真机 `-i` 装过了 —— 因为 20 的 `div#footer` 挂在 `<body>` 下、`<footer>` 元素在别处。
  反过来 `website.contactus` 那两个锚点是真死了（安装当场炸）。所以：默认不计失败，
  候选清单交给"能不能换成不依赖容器元素的锚"这道人工判断。
* **`t-esc` / `t-raw` 在 20 的服务端 QWeb 里已经没有了，而且不报错**。19 的
  `_compile_directive_esc`/`_compile_directive_raw`（19 `ir_qweb.py:2487/2497`）在 20 全文找不到，
  指令分发是 `getattr(self, "_compile_directive_%s")`（20 `:1924`）→ 取不到就跳过，
  只在 `:2031` 打一条 "Unknown directives or unused attributes" 警告，**那块内容直接消失**。
  所以这一类和 `read_group` 一样是"静默型"，只能靠静态扫。规则**必须排除 `static/` 目录**：
  OWL 的 JS 模板编译器仍支持 `t-esc`（20 core 剩下的 3 处 `t-esc` 全在 `static/src/**.xml`）。
  `t-esc`→`t-out` 等价（都转义）可机械替换；`t-raw` 不等价（`t-out` 只在值是 Markup 时不转义），
  只有"填空槽位"惯用法 `t-raw="0"` 可以机械换成 `t-out="0"`，其余必须人工判。
* 静态规则的**误报要显式承认**：`read_group` 规则会命中写在文档串里的 19 写法示例
  （我们自己的 `tests/test_tour_line_counts.py` 第 4 行就命中一次）。不改成 AST 级过滤是
  有意的——"把命中过滤掉"比"保留一条可解释的噪音"更危险（见 TDS-30 §5.6 第 13 行的教训）。

## 实测到的缺陷数量（19 源码 → 20 空库）

* 视图继承锚点：tour_* 77 个锚点里，静态报 13 处，其中 `tour_website` 的
  `/contactus` 页正文 2 处是真失效（20 的该页只剩表单），已删该记录并把
  `//footer//…` 前缀改成按文本锚定（`//a[@href='mailto:…']`、`//h5[text()='About us']`），
  这样两版都成立；另 2 处 `tour_accounting` 报的经实测是误报（模块已装绿）。

* 装载顺序 / 无 name menu：25 处（tour_accounting），其中 14 处是仅用于改父级的
  `ir.ui.menu`，`name` 只能从 19 现网取回。
* 真被 20 删掉的模型：`account.group`（19 现网表 0 行）、`hr.leave.type`（Webkul 工资单）。
* 真被 20 删掉的字段：`ir.actions.report.report_file`（tour_accounting 19 处 / 5 文件）。
* 消失的核心 xid menu：`account.root_payment_menu`、`account.account_logs_menu`、
  `account_payment.*_menu`、`hr_expense.menu_hr_expense_account_employee_expenses`。
* 服务端 QWeb 已删指令（`check_legacy_api.py` 全树 37 个模块）：**`t-esc` 440 处**
  （tour_* 418 / 其余 22）+ **`t-raw="0"` 2 处**（tour_guide_portal、tour_pm_portal 各 1），
  非 0 的 `t-raw` **0 处** —— 也就是说这一大片的转换是纯机械等价的。
  已适配树（`/tmp/b0/b1addons`）现在 `t-esc`/`t-raw` **归零**。
* `read_group` 回归网：`tour_fleet + tour_resource + tour_product` 三模块
  **47 个用例 0 failed 0 error**（2026-09-22，`/tmp/b0/rg_tests_4.log`）。里面 8 个是本轮新增的
  "非零分组"用例（每条都配 `search_count` 交叉核对），专打 20 那个"位置写反不报错只数错"的变更。
* `odoo.http` 导出收缩：19 生产树 **2 处**（同一个文件
  `tour_accounting/controllers/statement_report.py`：24 行 `from odoo.http import content_disposition`
  装不上，47 行 `http.serialize_exception` 只在 xlsx 下载报错时才走到）；已适配树 **0 处**。
* 前端 JS（`static/src/**/*.js`，两版树各 **30 个文件**）：20 **整层删掉了 `web.public.widget`**
  （实测 `odoo20/addons/web/static/src/` 全树已无该符号，19 还留着 legacy 层），`odoo.define()`
  的 AMD 包装也全面改成 ES module。19 生产树命中 **3 处、集中在一个文件**
  `tour_website_sale/static/src/js/tour_website_sale.js`（1 × `odoo.define` + 2 × `publicWidget`）；
  已适配树 **0 处**（该文件已重写为普通 ES 模块，`node --check` 通过）。
  **这一类装载全绿和冒烟 0 个 500 都不能证明没坏** —— JS 不被 Python import，页面状态码照样 200，
  所以必须靠静态扫。静态扫只证明"旧写法没了"，所以又补了三步（详见 TDS-30 §5.8 第 4 段）：
  真渲染商品页核对 DOM 契约 → 在打包后的 `assets_frontend` 里确认新模块确实进包 →
  `js_harness.mjs` 用最小 DOM 桩在 node 里跑真实文件（7 个断言：档位按 `name` 不按位置、
  坏 JSON/未选班期不抛、`input`/`change` 监听真的接上）。**唯一没做的**是真浏览器点一次，
  记在 B1 签字页的已知残留里。
* `request.website` 在 20 已删（19 由 `website/models/ir_http.py:265` 赋在 Request 上，
  20 改成 `env.website`，`odoo/orm/environments.py:303`）：**修前两版树各 1 处**（同一个文件的
  `_create_cart()` 兜底），装载期不报、GET 冒烟也不报，**POST `/shop/tour/add` 才炸 500**。
  已修（**20-only，不能回落到 19**）。顺手穷举了适配树用到的 10 个 `request.*` 名字，
  除 `website` 外 20 都还在。
* **负例冒烟**（`shop_neg_smoke.py`，4 条）当场抓出一个两版同源的校验洞：非法提交
  （缺班期 / 人数全 0）**返回"加购成功"**，购物车里静默多出一行 `departure_id=NULL`、
  单价 = 模板 `list_price` 的线路产品。⇒ 已把这两条判据提到控制器；
  并记下方法论：**"0 个 500"不等于"校验在工作"**。
* **Gate B1 全装判据（权威）**：`b1gate4` 空库 `-i` 19 个 tour_*（+ `purchase`）→
  **125 模块 / `Modules loaded.` / `0 failed, 0 error(s) of 129 tests`**，
  `tour_hr` 是唯一未装（F5 的 `hr.leave.type`）。逐条 WARNING 定性和复现命令见 TDS-30 §5.7。
  门户修复之后又在全新库 `b1gate5` 重跑一次，逐项相同（`/tmp/b0/gate_b1_5.log`）→
  说明这轮的模板/控制器改动没有动坏装载面。

* 门户运行时冒烟（装载 + 单测都不覆盖 `type='http'` 的控制器）：首轮
  `15×200 / 29×500 / 50 Traceback`，修完 4 类后 **`44×200 / 0 traceback / 0 ERROR`**，
  剩余非 200 全是"探针用的 `id=1` 不存在"和 1 个正确的 403。
  **假绿陷阱**：20 的 `/web/login` POST 不带 `csrf_token` 就 `login=400`，此时所有探针都在匿名会话上，
  而每个门户控制器都渲染自家 "No Access" 模板 —— 0 个 500 什么都不证明。
  所以测试账号必须①真登录 ②逐个显式授予门户组（`group in user.group_ids` 只认显式成员）
  ③有 `partner_id` 对得上的 `tour.guide` 记录。详见 TDS-30 §5.8。

* 冒烟顺带查出的 **19 现网潜伏缺陷**（两版核心代码逐字等价，不是 delta）：
  `<div t-call="portal.pager"/>` **14 处**（在 19 生产库上实测渲染 → 同样 `SyntaxError`，
  即这 14 个门户列表页今天就 500）、`t-att-*` 里的 `context_today()` **1 处**
  （服务端 QWeb 的注入名单两版都没有它）、`pager['limit']` **3 处**
  （`pager()` 的返回字典两版都没有 `limit`）。三条修法都是**两版等价**，可原样回落 19。
  `check_legacy_api.py` 新增 3 条规则（`t-call` 非 `<t>`、`t-att` 里 `context_today`、`pager['limit']`）：
  19 生产树报 **14 + 1 + 3**，已适配树报 **0**。

