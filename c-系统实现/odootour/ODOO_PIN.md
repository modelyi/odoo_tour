# ODOO_PIN —— odootour 版本固定记录

约定与 tms-platform/tour-platform 的 A0-5 一致：**一切镜像按 digest 固定，升级必须显式换 pin 并走一遍冒烟。**

## 当前 pin（2026-10-15 更新）

| 项 | 值 |
|----|----|
| 来源 | https://github.com/odoo/odoo（社区版，零 patch） |
| 分支 | `20.0` |
| commit | `122e465365d552cd4e40c9ee34dc5e79b1336cc1`（2026-10-15 分支头；上一 pin `c7f7429776e0`） |
| 构建方式 | 自建镜像 `Dockerfile.odoo`（Docker Hub 无官方 odoo:20 镜像，2026-09-25 用 registry API 核实；最新为 19.0-20260908） |
| 基础镜像 | `python:3.12.14-bookworm` @ `sha256:dbbe4ceb97851e2e5fa83798b239811f871cb743b259ba3563737349f6bcfaa0` |
| 数据库 | `postgres:16-alpine` @ `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| 镜像产物 | `odootour:20.0-a3` = image ID `82b1a97418db`（2026-10-15 升级 pin，配方与 a2 完全相同；旧产物 `20.0-a2`=`98049665c16d` 保留作回退） |
| 访问 | https://tour.solepro.cloud → nginx → 127.0.0.1:8079 |

## 升级 runbook（20.0.x 小步推进）

1. `git -C /tmp ls-remote https://github.com/odoo/odoo refs/heads/20.0` 选新 commit；
2. `make backup`（pg_dump + filestore）；
3. `.env` 改 `ODOO_COMMIT` → `make build`（新镜像 tag 建议 `20.0-aN` 递增）；
4. `make up` 重启；启动后访问 `/web/login` 冒烟 + 检查日志无 registry 报错；
5. 回退 = `docker compose up -d` 指回旧 tag 镜像（DB 兼容旧 commit 时）。

## 官方镜像切换点

一旦 Docker Hub 出现官方 `odoo:20`（library/odoo tags），可把 `Dockerfile.odoo` 改为
`FROM odoo:20@sha256:<digest>` 并删除源码 clone 层；挂载/配置/compose 均不需要变。

## 客制化路线

- 铁律：core 零 patch；客制一律放 `$ODOOTOUR_HOME/cust_addons` → 容器 `/mnt/extra-addons`（当前为空，仅预留）。
- B1 阶段挂 `c-系统实现/tour-platform/addons20` 的 35 个 20 侧模块；届时：
  - `.env` 注入 `TMS_FIELD_ENCRYPT_KEY`，且**必须与 tms 完全同值**（见 tour-platform compose 注释）；
  - pip 依赖按 `tour-platform/requirements20.txt` 的 pin 线（qifparse/pandas/numpy）追加进 Dockerfile。

## 目录布局（基准目录 /home/adai/odoo20tour，compose 变量 `${ODOOTOUR_HOME}`）

| 路径 | 角色 |
|------|------|
| `~/odoo20tour/odoodocker/` | 部署入口：compose/Makefile/Dockerfile 均为指向仓库的 symlink，可 `cd` 进去直接 `docker compose up -d` |
| `~/odoo20tour/conf/odoo.conf` | 容器实读配置（symlink → 仓库 `config/odoo.conf`，改仓库版即生效，restart 后） |
| `~/odoo20tour/cust_addons/` | 客制 addons → 容器 `/mnt/extra-addons`（仓库 `addons/` 是指向它的 symlink） |
| `~/odoo20tour/vendor/odooapps-20.0` | 第三方模块 → 容器 `/mnt/vendor-addons`（只读；仓库 `vendor/` symlink 指向此，不入库） |
| `~/odoo20tour/pg/postgres` | PG 数据 → db 容器 |
| `~/odoo20tour/pg/odoo` | Odoo data+filestore → `/var/lib/odoo`（属主须为容器 odoo uid 100） |
| `~/odoo20tour/backup/`、`odoo_log/` | make backup 落盘处 / 日志预留 |
| `~/odoo20tour/.env` | 与仓库 `.env` 同步（两处同内容，均 gitignore） |

仓库 `c-系统实现/odootour/` 保存全部可版本化文件（compose、Makefile、Dockerfile、config/odoo.conf、文档）。

## 第三方模块（vendor/）

- 来源：https://github.com/odoomates/odooapps 分支 `20.0`，pin HEAD `478c06f`（2026-09-25）。
- 说明：apps.odoo.com 下载需登录账号，免费模块改由厂商官方 GitHub 仓库获取，功能与商店发布包同源。
- 挂载：`/home/adai/odoo20tour/vendor/odooapps-20.0` → 容器 `/mnt/vendor-addons`（只读），已并入 `addons_path`；升级时在该目录 `git pull` 并更新此处 pin。
- 已安装（vendor 23 个中的 22 个口径）：`om_account_accountant` 全家桶（会计套件，69 模块）+ `om_account_budget_purchase`、`om_hr_payroll`、`om_hr_payroll_account`（2026-09-25 补齐，连带 core `purchase`/`hr`/`hr_holidays`）。
- **不装**：`om_data_remove`——批量删数据运维工具，显著放大删除权限，不入生产库；需要时临时装用。
- 迁移动态：`om_hr_payroll` 与 19 端 OH HRMS 套件（hr_payroll_community 等 14 模块）功能撞名，tour_hr 移植批（F5 待签字）时二选一，以 om 为基。
- 迁移战略（已定）：会计栈**以 om 为基础**，tour_accounting 原地瘦身为业务增量模块（保技术名，depends 切 om 全家桶），详见迁移计划 I1。

## 历史

- 2026-09-25 初始装机：20.0@87a1773bda6c，全新空库 `tour20`（无 demo），仅 core；
  取代 `/home/adai/odoo20` 源码 dev 实例（master 20.1a1，tag `tms-20.1a1-r1`，127.0.0.1:28069）。
  旧数据保留在 `odoo20-db` 容器不动。
- 2026-09-25 安装 `om_account_accountant`（odoomates/odooapps@20.0 pin `478c06f`，vendor 只读挂载），`-i om_account_accountant --stop-after-init` 无 ERROR，重启后 `/web/login` 200。
- 2026-09-25 运行数据迁至基准目录 `~/odoo20tour/`（odoodocker/conf/cust_addons/pg/vendor/backup，见上"目录布局"）；迁移前留档 `backup/tour20-prehome-20260925-123257.sql.gz`；仓库内 data 副本已删。
- 2026-09-25 补齐 om 套件：加装 `om_account_budget_purchase`/`om_hr_payroll`/`om_hr_payroll_account`（连带 core purchase/hr/hr_holidays）；`om_data_remove` 刻意不装。addons20 35 模块拷入 `cust_addons/`（未装载）。
- 2026-09-25 **清库重建 + 升级**：pin 升到 20.0@c7f74297（+5 官方 FIX），镜像 `20.0-a2`（含 tour pip 依赖层）；删除旧 `tour20` 与调试残留库，重建空库（base 无 demo）+ om 全家桶，现 83 个 installed。清库前备份 `backup/tour20-20260925-143237.sql.gz` + `filestore-20260925-143237.tgz`；旧镜像 a1 保留可回退（`docker compose up -d` 指回 tag + 恢复备份）。
- 2026-09-25 加装 `l10n_cn`（中国会计本地化），与 tms 19 生产口径一致（19 端 installed 的 l10n 也仅此一个）；共 84 个 installed，日志 0 ERROR。

- 2026-09-26 **M2 影子库验收**：tour20_dev 加装 core `account` + `ta_order`/`ta_finance`，
  四模块 26 个测试全绿（exit 0）。正式库 tour20 未动，待 M4 端到端后安装。
  Odoo 20 API 坑位记录（供后续模块）：① 视图按钮 `states=` 属性已废除，用 `invisible="state ..."`；
  ② `res.users` 组字段改名 `group_ids`（且命令值须传 id 整数）；③ `account.account` 无 `company_id`（跨公司模板）；
  ④ 冲销字段为 `reversed_entry_id`/`reversal_move_ids`（无 `reversal_move_id`）；⑤ 无 `fields.Related`，related 走字段参数 `related=`。
  ta 出纳/会计组在 ta_finance 中挂 `account.group_account_invoice`（凭证生成最小权限）。
- 2026-09-26 **M3 影子库验收**：`ta_dispatch`（派工条目+确认生成供应商账单草稿+取消回退）与
  `ta.team.pnl`（SQL 视图，BS-19 口径：cost_net=cost/(1+r)，含税口径单列）安装通过；五模块 30 测试全绿。
  新增 20 端坑位：⑥ `ir.config_parameter` 改类型化 API（get_bool/set_float…，无 get_param）；
  ⑦ partner 级 `property_account_expense_id` 移除，费用科目走 `company.expense_account_id`；
  ⑧ pivot/graph 不接受 create 属性；⑨ SQL 视图模型测试读取前需 `env.flush_all()`。
- 2026-09-26 **M4 正式库安装**：`ta_guide`（借款-审批-发放挂 1221 口径科目 icp `ta_guide.loan_account_id`、
  报账审核入单团成本、佣金 BS-08 AC-18 税后净额冲抵）六模块全套装入 tour20（安装前备份
  `backup/tour20-pre-ta-install-20260926-111424.sql.gz`），tour20 现 90 installed；restart 后 /web/login 200。
  影子库回归 36 测试全绿（六模块）。导游对账 portal 界面留批3（规则与数据链已闭环）。
  生产使用前需配置：公司费用科目、导游借款科目（1221）、银行日记账默认科目（发放/落账依赖）。
- 2026-09-28 **财务迭代 3/4/5 坑位补录**（批1/账龄/绩效/景点毛利实测）：
  ㉑ 跨模块字段依赖：ta_order 不能引用 ta.payment.claim（加载次序），字段与钩子放依赖方 `_inherit` 扩展；
  ㉒ O20 XML RNG：`pivot/search create="0"`、search 内 `<group>` 均非法，分组走 list view grouping；
  ㉓ O20 m2m 关系表列名 = 完整模型名（`ta_departure_id`/`res_users_id`），自定义 rel 名保留给定列名；
  ㉔ PG 无 `round(double precision,int)` → 先 `::numeric`；
  ㉕ Float 无 default 可能存 NULL → SQL 视图 COALESCE + 字段显式 `default=0.0`；
  ㉖ 测试创建 partner 时 `property_account_receivable_id` 必须传 `.id` int（recordset 不可 JSON 序列化）；
  ㉗ 会计组用户无派工创建权限，测试造派工条目需加 `ta_base.group_ta_dispatcher`；
  ㉘ security CSV 手工 printf 会吞 domain 引号，用 sed/heredoc 修复后必 grep 复核。
- 2026-09-28 **迭代6 迁移（tms19→tour20）run1 坑位**：
  ㉙ `odoo-bin shell < script` 模式 `__name__=='__main__'` 成立，main() 自动执行；
  ㉚ run1 容器副本曾把 chunk_update 的 mogrify 值**追加**到 SQL 尾部（`%s` 占位未替换 → PG 语法错误）；
     仓库版已改为 `%`→`%%` 转义 + 首个 `%%s` 还原替换；模板含 `LIKE 'ETM|%'` 时此坑必踩；
  ㉛ account.move.line 手建分录借正贷负：应付/权益须传负额，否则 `debit=max(amt,0)` 全进借方，
     create 即 "not balanced" UserError；
  ㉜ 对平校验 SQL 要按科目过滤（V13 曾对整张平衡凭证求净额，恒 0 造成假差异）；
  ㉝ 跨库读旧系统：`docker network connect tms-net odootour-odoo` + psycopg2 双连接，口令仅 env 注入
     （`TMS_OLD_DB_PASSWORD`，值同 tms-odoo 容器 PGPASSWORD），跑完 disconnect 还原；
  ㉞ O20 `account_account.code` 是 compute（公司相关），raw SQL 只能查 `code_store->>'<公司id>'`；
     对平脚本校验 SQL 异常时回退打印预测值=自我印证，必须显式报错而非吞掉；
  ㉟ SQL 视图改 id 列类型（integer↔text 拼接）时 `CREATE OR REPLACE VIEW` 报
     `cannot change data type of view column`，init() 必须先 `DROP VIEW IF EXISTS`；
  ㊱ 建 `account.account`（account_type=asset_cash）会级联 `_create_default_journals` 自动生成
     无 code 日记账，别名 `bank-none` 撞存量 → 迁移后测试造银行数据须复用存量日记账；
     迁移后 tour20 常驻真实数据，dev-test 造数一律 get-or-create（按 code search-first），
     聚合断言选存量未覆盖的远未来月份，防数据污染型 FAIL。
- 2026-09-30 **批3-4 正式迁移（成本明细/借支）坑位**：
  ㊲ store=True compute 字段（如 ta.guide.loan.deducted_amount/outstanding，依赖 One2many 冲抵行）
     建后 raw SQL 直写，会被后续 flush/重算**静默覆盖回计算值**（迁移直写残留不可靠）；
     历史存量数值若无来源记录（冲抵行/凭证）不应造直写 → 按模型口径导入 + 差额如实报告；
  ㊳ 迁移脚本对账项（V 系）判定为"差异!"时 devops 必须停跑回报，不得自行解释放行——
     阶段B 正是靠此门禁在 V6b 拦截了 ㊲（EXIT=0 不代表对平）；
  ㊴ odoo 容器内 /tmp 脚本属主 uid=1002 时 `sed -i` 需 `docker exec -u root`（默认 odoo 用户 100 无写权）。
  ㊵ 批2 用 raw SQL 批量插入的表（如 ta_receivable_plan）**不会有 ORM 外键索引**（索引只在
     ORM create/字段升级时生成）→ 依赖它的 SQL 视图按行做相关子查询时退化为 N×全表扫：
     应收账龄首屏 ORDER BY+LIMIT 80 实测 3 分钟（冷缓存同量级）。修法两条都要做：
     ①字段补 `index=True` 并 `-u`（psql 手工建的索引会在下次 schema 升级前一直在，但代码里没有=不可复现）；
     ②视图把相关子查询改为一次性预聚合 CTE + LEFT JOIN（16k 行视图 3min → 101ms）。
     另可加偏索引 `ON ta_order (state) WHERE amount_open > 0.01`（未收单只占 20%）。
     教训：SQL 视图 count(*) 快 ≠ 首屏快，必须按 `_order` + LIMIT 的真实形态测。
- 2026-10-15 **常规升级 a3**：pin 升到 20.0@122e4653（上游 20.0 分支 20 天增量官方 FIX）。
  升级前备份 `backup/tour20-20261015-132153.sql.gz` + `filestore-20261015-132153.tgz`；
  镜像 `20.0-a3`，compose tag 已同步。冒烟：容器内 HEAD=122e4653、启动 0 ERROR、
  92 modules loaded、`/web/login` 200（127.0.0.1:8079 与 https://tour.solepro.cloud 均验）。
  回退：`docker compose up -d` 指回 tag `20.0-a2`（a2 镜像保留）。
  已知无害 WARNING（a2 起即有，非本次引入）：odoo.conf `gevent_interface` 未知选项、
  markdown2 未装、ta_* 字段 `tracking` 参数不识别。
- 2026-10-15 **退役归档 ~/odoo20 源码 dev 实例**（master 20.1a1@c89bb6b64，2026-09-23 起停用）：
  旧实例全量归档至 `~/odoo20-retired-20261015/`（源码+filestore tgz、odoo20-db 全部 24 库
  pg_dump -Fc 253M、SHA256SUMS、恢复说明 README），随后删除 `~/odoo20` 目录、
  `odoo20-db` 容器与 `odoo20-pgdata` 卷，释放约 8G，端口 5434 已释放。
  上表"旧数据保留在 odoo20-db 容器不动"的约定自此由归档目录承接。
