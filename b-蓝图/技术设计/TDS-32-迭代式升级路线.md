# TDS-32 迭代式升级路线（每一步都有人能看见的成果）

> 状态：现行执行路线（2026-09-22 起替代 TDS-30 §7/§8 里"B1 全做完 → B2 全做完 → B3 一次切换"的大爆炸形态）
> 触发：用户决定 ——「最好迭代式的升级，可以逐步的让人看到成果」
> 关系：本文**不推翻** A0/A1/A2 与 B0/B1 的判据，只重排 B2/B3 的**交付形态与顺序**；
> 所有已实测的 19→20 事实仍以 [TDS-30](TDS-30-迁移架构与ETL设计.md) §5.7/§5.8 为准。

## 1. 迭代能迭代什么：一条硬边界

**能迭代的是"准备与验证"，不能迭代的是"写入权"。**

19 与 20 是两个结构不同的库（20 把 `inalterable_hash`/`restrict_mode` 哈希链带进了社区版，
15 个字段由存储翻成非存储，见 TDS-30 #23），**没有双向同步**。所以按 URL 把"财务留 19、门户切 20"
这种拆法看似聪明，实际是把一份业务数据变成两个真相源。

再收紧一层：本系统里 **订单 ↔ 班期 ↔ 凭证是写耦合的**
（`tour_order` 生成 `account_move`、`tour_accounting` 回写核销与 `matching_number`），
这三者的**写入权必须同一切片转移**。可以拆开先切的，只有"只读面"。

⇒ 路线形态：**只读面可以逐步切给业务用；写入权一次性转移，但窗口只覆盖账本+订单。**

## 2. 四个可演示的台阶（每级都有人能用、能签字的东西）

| 台阶 | 交付什么 | 谁看得见 | 风险 | 判据 |
|---|---|---|---|---|
| **S0 影子可见**（本周起） | 20 实例灌入 19 的**真实数据**，挂 `tour20.solepro.cloud`，**全站只读**（演示账号 + `default_transaction_read_only`）。业务能在 20 的界面上查自己的线路、班期、单据、报表 | 全公司 | 零（19 不改一行，20 可随时删库重建） | 主数据/账本行数与金额对账 0 差异（用 B2 的 recon 三件套） |
| **S1 只读门户切流** | 把**只改读不改写**的门户面按 URL 前缀切到 20：官网 `/tours`、`/shop`，导游门户 `/my/guide`（列表/详情），CFO/COO/PM 的报表页 | 导游、市场、管理层 | 低（写仍在 19；nginx 回指 = 秒级回滚） | §5.8 四段判据 + 该 URL 集负例冒烟 + 一周双跑比对 |
| **S2 写入权转移** | 账本 + 订单 + 班期的**写权**整体转到 20，`tour.solepro.cloud` 指 20；19 转只读回退 | 财务、计调 | 中（唯一需要冻结窗口的台阶，目标 4–6 h） | 两次完整 dry-run 0 差异（TDS-30 §8 Gate B2）+ 回退演练过一次 |
| **S3 收尾** | `web.base.url`/SMTP 实配、锁日期、序列 `next_number`、restrict_mode 哈希链重建、19 只读保留期决定 | IT、财务 | 低 | 邮件实测收到 + 凭证能过账且哈希链连续 |

**S0/S1 期间 20 库反复重建**：每次重建 = 上一次的水位 + 增量 ETL，跑一次记录一次耗时，
所以 S2 的窗口长度是**测量出来的**，不是估的。这是迭代路线相对原计划最大的降险收益。

## 3. 与 A 阶段（19 平桥）的关系：不互相阻塞

A1 的域名翻转（`tour.solepro.cloud` → 19 平桥实例）**不需要**业务冻结之外的授权，
只需要一个 4–6 h 写入冻结窗口；它与 S0 可并行：

- A 阶段解决的是"现网风险"（备份未验证、`/web/database/manager` 可达、`admin_passwd` 明文、密钥来源不明）。
- B 阶段解决的是"升级"。
- 两件事共用的只有 `tour.solepro.cloud` 这个域名和一次真机演练的机会 ⇒ **A1 的 dump/restore/核对流程就是 S0 的 ETL 第一次彩排**，脚本复用。

若 A1 的冻结窗口迟迟拿不到：**S0 照做**（它只读，不碰域名），A 阶段降级为
"在现网原地做 A0 加固 + 恢复演练"，记为已知问题，不拖住 20 的可见成果。

## 4. B1 模块适配也按台阶排，不追求"21 个一次全绿"

已达成（不必再等）：**20 个 tour_ 前缀模块在 20 空库 `-i` 全绿 + 129 单测 0 失败**（TDS-30 §5.7 权威列，`b1gate8`）。

按台阶解锁，被挡的模块后置：

| 台阶需要 | 模块 | 状态 |
|---|---|---|
| S0/S1 | `tour_base` `tour_product` `tour_resource` `tour_fleet` `tour_order` `tour_accounting`(只读报表) `tour_*_portal` ×5 `tour_website` `tour_website_sale` | **已绿** |
| S2 | `tour_saas` | **本期停用**（20 无运行时建库 API；全仓无依赖；租户表仅 1 行测试数据） |
| S2 | `tour_hr` | **唯一未装**，被 F5（`hr.leave.type` 的 20 侧变更）挡住 → Webkul OHRMS 14 件同一批处置，**不挡主链**，S2 之后再评估 |

⇒ "21 个模块一次全绿"这个原计划判据正式改成：**主链 20 个全绿 = B1 通过**，
`tour_saas` 停用与 `tour_hr` 后置写进 B1 签字页的口径差异。

## 5. 节奏（每周都有可看的东西）

| 周 | 做什么 | 结束时别人能看到 |
|---|---|---|
| W1 | B1 签字页（含口径差异）；A0 三件事收尾；S0 第一次全量 ETL（主数据+目录象限） | `tour20` 上能看 19 的线路/班期/导游目录 |
| W2 | S0 账本象限（不可变历史整表 INSERT 保留原 ID）+ 对账报告；A1 冻结窗口若到位则翻域名 | 财务在 20 上查总账/余额，与 19 逐单元格比 |
| W3 | S1 只读门户切流（`/tours` `/my/guide` 报表页）+ 一周双跑 | 导游和领导真的开始用 20 的页面 |
| W4–W5 | S2 两次完整 dry-run 计时；末次窗口切流 | 生产在 20 上，19 变只读回退 |
| W6 | S3 收尾 + 回退演练（回切再切回） | 发布说明 + 已知问题清单 |

## 6. 每条增量的技术不变式（S0 起每次重建都要过）

1. **保留原 ID**：象限 1（`account_move`/`account_move_line`/`account_partial_reconcile` 及 m2m）
   整表 INSERT 带原 ID + `setval` 序列 ⇒ `matching_number == str(full_reconcile_id.id)` 自动成立。
2. **XMLID 不断**：拷 `ir_model_data` 并保留 `noupdate`，否则 20 上升级模块会重复造记录。
3. **15 个非存储字段永不进 SQL／`order=`**（TDS-30 #23 清单）。
4. **约束名按 20 的新名字认**（`tour_account_period_uniq_code` 等三处，#4 段末尾）。
5. **门户准入要显式组成员**：`res_groups_users_rel` 直拷 + 核对 `res_groups_implied_rel`，
   靠 implied 继承拿到的组在 `_is_*_user()` 判据里**不算**（§5.8 前提②）。
6. **附件**：`ir_attachment` 走象限 1，filestore `rsync -a` 保留属主（uid 不一致 → 附件 500）。
7. **负例进 UAT**："没有 500"不等于"校验在工作"（TDS-30 #25）。

## 6A. S0 实测出的五个通用通道（`scripts/migration/`，S2 复用同一套）

搬运管线里"一次失败换一条规则"的部分全部落在 `etl_slice.sh` 头部注释（九条铁律）。
真正需要设计的是**五个通道**，因为 19→20 的坑不是一类，是五类，混在一个通道里必然互相掩盖：

| 通道 | 什么时候用 | 为什么不能合并 |
|---|---|---|
| `slices/modes_s0.txt` 的 `insertignore` / `skip` | 源侧自己就违反目标唯一键；或该表**由 20 拥有**（装模块就重建） | 前者是"能搬的先搬，违约的定性"，后者是"根本不该搬" |
| `slices/remap/<表>.txt`（`@ref` 镜像 + staging UPDATE） | 两侧都有这列、但外键 id 不同（模块基数据） | 重映射必须在**目标库**做：源库的 SELECT 看不见 20 的表 |
| `slices/fixcol/<表>.txt`（SQL 规则填列） | 20 新增的列 19 根本没有值，但值**可按规则推导** | 补 staging 救不了它 —— 该列不在两侧交集里，进不了 INSERT 列表（铁律 9） |
| `slices/exclude_s0.txt`（排除列） | 20 新增的列 19 连**落点**都没有 | 不编造值，只留痕，进待签字清单 |
| `s0_grant_groups.py`（XMLID 自然键映射） | 关系表的**端点是 20 自建的组**（`res_groups` 在 DENY 名单里，两侧同组不同 id） | 按原 id 拷 = 把用户挂到**别的组**上，是权限放大，比不拷更糟；只有自然键能对得上 |

`etl_order.py` 除了出顺序，还出 **`slices/cycles.txt`（拓扑时剪断的回边）**，交给
`etl_cycle.sh drop/add`：搬之前摘掉环上的外键，搬完原样加回。
这一步是必须的 —— 只按顺序搬永远不收敛，因为 **`INSERT … SELECT` 是一条语句 = 一个事务**：
`account_move.origin_payment_id ↔ account_payment.move_id` 互相引用，27.6 万条凭证里
只要有一条指向还没搬的付款，**整表 0 行进不去**（实测两轮都失败）。
`add` 那一侧不是保险，而是**引用完整性校验本身**：加不回去的那条就是真脏数据，
和"顺序问题"从此彻底区分开 —— 这正是 B2 对账要的输入。

回边判定必须剔掉 `create_uid`/`write_uid`：Odoo 每张表都指 `res_users`，DFS 里"到处都在栈上"，
第一版因此报了 202 条回边（真环 122 条、摘除 218 个约束），照单全 DROP 等于把约束校验废掉。

S0 实测的 19↔20 语义变更（B2 待签字清单的来源，不是实施细节）：

1. **`res.bank` 模型在 20 被整个删除**（19 有 60 行）⇒ `res_partner_bank.bank_id` 无处可去，
   开户行名称这一栏会丢；20 用 `clearing.label`（13 条，1 条国家级为 NULL 的默认标签）替代。
   实测 19 的 97 条收款账户里 `clearing_number` 非空 **0** 条，所以只丢名称、不丢号码。
2. **`account_move` 新增 CHECK**：发票类凭证的 `document_tax_mode` 必须非空
   （`account_move.py:836`），取值语义 = 公司设置 `account_price_include`（现网单公司，两侧都是
   `tax_excluded`）。该列**可空**，所以任何只看 `attnotnull` 的自动兜底都看不见它。
   风险留痕：旧凭证在 20 里被**编辑**时会按新语义重算税额 —— 只读看数无影响，写路径要业务确认。
3. **`payment.method.provider_id`：19 的 m2m 在 20 变成 NOT NULL m2o**（19 有 231 行派生目录，
   20 只留 3 行）⇒ 判定为"20 拥有"，不搬。
4. **一批 20 新增 NOT NULL 列**（`res_country.zip_applicability`、`hr_version.tz`、
   `sale_order.document_tax_mode` 等 11 张表）：有 DB 默认用默认，否则按类型兜底，
   外键列兜不出 id 就删该行 —— 每条动作写进 `FILLLOG`（本轮 740 处补默认 / 176 处删行 / 42 处无兜底）。
5. **filestore 是 `tms` + `tms_tenant_1789530161` 两个目录的并集**：415 个对象的实体在租户目录里
   （内容按 sha1 寻址 ⇒ 可安全合并去重）。A1/B2 的附件拷贝必须按这个口径，否则附件 404。
   判据也不能用"行数 = 文件数"：19 侧 27,564 行只对应 **3,197** 个去重文件（内容寻址共用），
   按行数判会误报"丢了两万多个文件"。
6. **中间表（m2m）对外键闭包是不可见的** —— 闭包沿"谁 FK 到谁"走，而没有任何表 FK 到中间表，
   于是父表全搬齐、中间表仍然 0 行。实测缺口：`account_move_line_account_tax_rel` 4,437→0、
   `product_taxes_rel` 233→0，表现成"凭证金额分毫不差，但税不见了"，逐表行数判据完全看不见。
   修法是 `etl_order.py::junctions()`：恰好两条外键、且两端都在（或允许在）闭包内的表补进来
   （实测补 52 张），同时把端点是 20 自有表的 11 张（`res_groups_users_rel` 等）单独列为
   "需自然键映射"，**绝不按 id 拷**。
7. **权限组成员必须走自然键**：不做的后果不是"少数据"而是**业务看不见** —— 影子库里所有
   `tour.*` 都是 AccessError，看着像搬迁失败。实测 19 侧 admin 有 32 个显式组（含
   `tour_base.group_tour_guide_manager`/`group_tour_operator`，正是 `tour.guide` 那两条 ACL 的组），
   20 侧空库只带 13 个装机组 ⇒ 必须按 `module.name` XMLID 两侧各解一次再写关系。
   映射不上的 XMLID 不猜不造，原样打印 = "切换后要重配权限"清单（B3 交付物）。
8. **安全规则表在 20 换了名字和形状**（B1 已按此重写 `ir.access`）：
   19 `ir_model_access`（`perm_read/write/create/unlink` 四个 bool + `group_id` 单组）
   → 20 `ir_access`（`model_id` m2o + `group_id` + **`operation` 一列字符串**，实测取值是
   `c/cr/cru/crud/r/rd/…` 15 种组合）。两张表**名字不同** ⇒ 不在两侧交集里，永远不进搬运清单，
   规则完全由 20 侧模块装载产生 —— 这是对的，但也意味着"19 里手工调过的权限"必丢，B3 要复核。
9. **20 的 web 层 RPC 协议变了**（`s0_smoke.py` 实测，S1/S2 前端与脚本都受影响）：
   `web_search_read(domain, specification, offset, limit, order, count_limit)`（19 是 `fields`）、
   `web_read_group(domain, groupby, aggregates, limit, …)`（19 是 `groupby_list` + `fields`）、
   `web_read(specification)`、`get_views(views)` 的 views 改成 **`[[view_id, view_type], …]`**
   （19 是 `[{type: …}]`）。⇒ 冒烟判"数据在不在、视图编不编得出来"一律走仍兼容的 ORM 级
   `search_read` / `read_group(domain, groupby, aggregates)`，不绑死在某个 web 协议版本上。
10. **翻译列在 19/20 都是 jsonb**：`res_groups.name` 直接 `string_agg` 报
    `function string_agg(jsonb, unknown) does not exist` ⇒ 任何跨版本 SQL 取"名称"都要
    `->>'en_US'` 或 `jsonb_typeof` 分支（`etl_slice.sh` 铁律 4 的类型转换正是为此）。
    `ir_model_data` 反倒**两侧同名**（`module/name/model/res_id/noupdate`，实测列一致），
    所以 XMLID 自然键映射在两侧都能直接用同一句 SQL —— 别凭印象给 20 编一个 `xml_id` 列名，
    凡跨版本取元数据一律先查 `information_schema`。

## 7. 变更影响与回退

- 本文替代 TDS-30 §7/§8 的**顺序**，不改其**判据**；判据逐条继承。
- 回退：S0 删库重建（零影响）；S1 nginx 回指 19（秒级）；S2 见 [TDS-31](TDS-31-回退预案.md) 的 R-B3。
- 待签字口径差异（不再单独等确认，按本文推进并在签字页说明）：
  ① 模块面 20 个（非"21 去掉 tour_saas"）；② 前端 JS 判据无真浏览器点击（node DOM 桩 + 渲染 + 状态码三层）；
  ③ `tour_saas` 多租户 SaaS 化移出本期范围；④ 19 现网已实测坏掉的 14 处 `t-call`／3 处 `pager['limit']`／
  1 处 `context_today`／班期校验洞，**是否单独回落 19 分支**（修法两版等价，除 `request.website` 那条只能留在 20）。
