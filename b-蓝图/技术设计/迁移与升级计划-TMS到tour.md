# TMS → tour.solepro.cloud 迁移与升级计划（19 平桥 + 20 升级）

> ⚠️ **已废止（2026-09-25）**：用户裁定不做数据与功能迁移，本计划自本日起停止执行，仅存档（A0/A1/B0 验收报告保留于 d-交付验收）。
> 后续方向见 [PRD-V20](../产品设计/PRD-V20-旅行社行业应用产品规划.md) / [TDS-V20](TDS-V20-模块地图与迭代批次.md)。

> 状态：**已批准并执行中**。A0 已完成（`d-交付验收/A0-Gate基线加固报告_2026-09-21.md`）；
> A1 平桥的数据等价性与金样例已通过，**域名切换与源库冻结待授权**（`d-交付验收/A1-平桥验收报告_2026-09-21.md` §7）；
> B0 可行性 spike 已通过 gate（`d-交付验收/B0-Odoo20可行性spike报告_2026-09-21.md`，矩阵与 diff 见 `b-蓝图/技术设计/TDS-30-迁移架构与ETL设计.md`）。
> **B0 带来的计划修订**（不改范围，只改工作量与顺序）：① §7 B1 需新增「`ir.model.access`+`ir.rule` → `ir.access` 全量重写」工作包
> （20 删了这两张表，原计划未量化）；② 模块 manifest 版本号必须改成 `20.1.x`（2–5 段）才可能被安装；
> ③ B1 的两个共享前置（`tour.bank.account` 去 `res.bank`、security 转换脚本）必须先做，否则逐模块只能看到同一个首失败；
> ④ §11 风险 ② 收敛为「Webkul 7 个模块阻塞在 20 假勤重构（`hr.leave.type` 被删），需 B0-Q1 业务确认后再估工」。
> 本文件是批准版计划的仓库内副本（原件 `~/.qoder-cn/plans/lone-quarry-colt.md`）；
> 两者若出现分歧，以本文件随阶段更新的结论为准。

## 1. Context（为什么要做、达成什么）

TMS 目前跑在 `tms.solepro.cloud` → 容器 `tms-odoo`（Odoo 19.0.1.3，主库 `tms` 2.6 GB）。已有一个 Odoo 20 源码实例（`/home/adai/odoo20`，master = 20.1a1，uv 环境，`127.0.0.1:28069`）临时挂在 `tour.solepro.cloud` 上。目标：让 `tour.solepro.cloud` 成为 TMS 的新入口，并把整套系统升级到 Odoo 20。

**已确认的决定性约束**（决定了方案形态，不是可选项）：
- Odoo 官方源码**不含任何 19→20 数据迁移脚本**（`odoo/addons/*/migrations/` 目录不存在；19 容器内同样没有），跨版本升级脚本只在 Odoo 官方升级服务侧。
- **OCA/OpenUpgrade 仓库分支最高到 19.0，没有 20.0**。
- → 自托管 Community **无法原地跨版本升级数据库**。B 阶段必须走"20 空库 + 函数式/SQL 混合数据搬迁"。

**已确认的范围决策**（用户选定）：分两步（先平桥 19，再升 20）；B 阶段基线用 master 20.1a1；数据全量迁移；OHRMS 14 个 + web_responsive 一并评估升级。

**真实数据规模**（比初判更大）：`account_move` 276,548 / `account_move_line` **818,693** / `ir_attachment` 27,832 / `ir_model_data` 38,415 / 活跃用户 90 / tour_* 表 51 张 / 已装模块 187 / 单公司 / 租户库 `tms_tenant_1789530161` 75 MB。

## 2. 域名与实例不变式（贯穿全程）

任一时刻，**每个域名只对应一个身份唯一的实例**；域名变更动作永远只是"改 nginx upstream + reload"，不夹带其它变更。

| 域名 | A0–A1 | A2–B2 | B3 终态 |
|---|---|---|---|
| `tour.solepro.cloud` | 收回（暂停服务或 301，**先做**） | 19 平桥实例（正式） | **20 实例（新生产）** |
| `tour-staging.solepro.cloud` | 19 平桥验收 | 停用 | 停用 |
| `tour20.solepro.cloud` | — | 20 适配/dry-run/UAT | 停用或留作预发 |
| `tms.solepro.cloud` | 19 生产（不动） | 19 生产 | 19 **只读回退** |
| 本机 28069（20.1a1 源码） | 收回公网 | 仅 SSH 隧道访问 | 即 20 实例载体 |

> 待办：`tour-staging` / `tour20` 需要在 Cloudflare 加 A/CNAME 记录（现为 `*.solepro.cloud` 通配代理，可能无需改动，A0 阶段实测确认）。

## 3. Phase A0 — 基线加固（旧环境原地，3–5 天；不碰域名、不碰数据）

| # | 动作 | 关键文件 |
|---|---|---|
| A0-1 | **备份恢复演练**：现有备份未验证过就不许当平桥输入。修 `backup.sh`：`tms` + 租户库**双库**、pg_dump 输出为 custom 格式但文件名改 `.dump.gz`（现名 `.sql.gz` 会误导成 SQL 文本）、去掉吞错的 `2>/dev/null`、filestore 纳入备份、异地/异盘保留 | `/home/adai/tms/backup.sh` |
| A0-2 | **加密密钥审计**：确认 `TMS_FIELD_ENCRYPT_KEY` / `ir.config_parameter('tms.field_encrypt_key')` 的实际来源与**密文列清单**（缺密钥会静默降级明文 → 搬迁时污染不可逆）。只核对来源与列清单，不输出密钥值 | `addons/tour_base/models/field_crypto.py` |
| A0-3 | **收掉公网暴露面**：现网 `list_db=True` + `admin_passwd=123456` 明文 → `/web/database/manager` 在 CF 后面可达。改 pbkdf2 哈希、`list_db=False`、加 `dbfilter`；口令进 `.env`（compose 里 env 被 `:ro` 挂载的 conf 全量覆盖，历史上从未生效） | `config/odoo.conf`、`.env`、`docker-compose.yml` |
| A0-4 | **20 dev 实例收回**：`tour.solepro.cloud` 从 20 源码实例摘下；20 实例只保留 `127.0.0.1:28069` + SSH 隧道/CF Access | `/etc/nginx/conf.d/tour.solepro.cloud.conf` |
| A0-5 | **镜像与依赖 pin**：`odoo:19` 按 digest 固定；`Dockerfile.odoo` 里 `pip3 install qifparse pandas` 补版本号 | `Dockerfile.odoo` |
| A0-6 | 清理：孤儿 filestore `tms_tenant_1789529976`（DB 已不存在）归档；Exited 临时容器列表化待清 | `data/odoo/filestore/` |

**Gate A0**：① 从当日备份拉起一次性库 + filestore，行数/文件数/抽样附件可读=恢复演练通过；② 新口令登录正常且 `/web/database/manager` 不可达；③ 密文字段清单与密钥来源有书面结论；④ 备份产物含双库 + filestore。
**回滚**：A0 各项均为单文件 revert，cron 可回滚。

## 4. Phase A1 — 平桥（纯复制，不掺任何配置变更，5–8 天）

1. 冻结源：`UPDATE ir_cron SET active=false`（27 个 active cron 会双跑，含 tour_accounting 的 recurring invoice/payments），停 `tms-odoo` 写入或整站维护模式。
2. `pg_dump -Fc tms` → 新项目 `c-系统实现/tour-platform/`：compose 项目名 `tour`，镜像与 A0 pin 完全一致，`tour-db`（postgres:16-alpine）里 `pg_restore --no-owner --role=odoo` 到新库 `tour19`（filestore 目录名必须等于目标库名），`rsync -a` filestore（**保留属主**，filestore uid 与新容器 uid 必须一致，否则附件 500）。
3. 配置**逐字节沿用** A0 版 conf（除 `dbfilter`/端口/日志路径），**本阶段不动 dev_mode、不动 workers**（每项变更各自独立回归，见 A2）。
4. `tour-staging.solepro.cloud` → tour 19 实例，做验收。
5. 一致性核对（全部要求 0 差异）：逐表行数、`account_move_line` 每账户 `sum(debit)=sum(credit)`、`sum(amount_total)`、`ir_attachment` 计数与文件数、`ir_model_data` 计数、`matching_number` 抽样、90 用户密码哈希可比对、filestore 抽样可读。
6. UAT 冒烟 ≥ 4 组金样例链路：登录/权限、财务过账+核销、导游门户、财务报表出数（与 19 逐单元格比对）。

**Gate A1**：核对报告 0 差异 + 冒烟通过 → 把 `tour.solepro.cloud` upstream 改指 tour 19（一行 + reload），A1 结束。
**回滚**：nginx upstream 回切，秒级；tms 全程未动。

## 5. Phase A2 — 标准化（每项独立提交、独立回归，3–5 天）

按风险从低到高逐项做、每项一次提交：① 去 `dev_mode=reload,qweb`（**这是行为变化不是修复**：QWeb/asset 缓存与 cron 并发画像会变，需单独回归）→ ② `workers` 按 `2×CPU+1` 公式定值并压测 → ③ 日志出容器（现在 `logfile=/tmp/odoo-server.log` 重建即丢）→ ④ healthcheck + `restart` 策略 + compose 版本化 → ⑤ 启用迁移台账（见 §8）。
**redis 会话**：社区版 19/20 的 `odoo/tools/config.py` **没有** session redis 选项，`web_session_store` 属 EE → **不作为 gate**，`tms-redis` 明确标记为闲置资源。
**Gate A2**：每项变更前后有性能/功能基线对比；UAT 回归通过。

## 6. Phase B0 — 20 可行性 spike（1–2 周，可与 A 并行）

产出《模块处置矩阵》（187 个已装模块逐个 port / replace / abandon + 工作量），依据：
- **19↔20 字段 diff 报告**：两侧各取 `information_schema.columns` 快照（19 现网 vs 20 空库），join 出新增/删除/类型变化，覆盖 tour_* 依赖的全部官方模型（account.*、hr.*、fleet、product.*、res.partner/users/company、portal/website 模板）。
- 已探明的 20 侧硬事实：`odoo.service.db` **整体消失**（只剩 common/model/server）→ `tour_saas` 的 `_create_empty_database`/`check_super`/`exp_drop` 在 registry 加载期 ImportError，**连安装都过不去**；`_frontend_pre_dispatch`（http_routing）**仍在**；`publicWidget` 注册表**已移除**（19 还有 legacy 层）→ `tour_website_sale` 前端 JS 必须 OWL 重写；`@web/views/kanban/*` 与 `action_manager` 路径**仍在**（多为改导出名）。
- OHRMS 14 件（Webkul 系）+ web_responsive：在 20 空库直接试装，按结果决定"上游 20 包 / 自研移植 / 砍"。
- 20 社区版原生**仍无总账/余额表**（`account/report/` 无 general_ledger/trial_balance），且把 **inalterable_hash / restrict_mode 完整性校验带进了社区版** → 启用 restrict_mode 的 journal 迁移后要重建哈希链。

**Gate B0**：矩阵 + diff 报告成文，B1 工作量与范围据此冻结。

## 7. Phase B1 — 模块适配（30–60 人日，最大不确定源）

铁律：**odoo core 零 patch**，一切绕过放 addons（monkey patch 必须挂跟踪单），基线 `git tag` pin 住。

**tour_accounting 判定顺序（可执行）**：
1. **分箱**：A 箱 = 自包含新模型（asset/followup/recurring/bulk payment/xlsx mixin/legacy 报表向导；19 与 20 上游都没有 `account.common.*`，该 fork 自带抽象基类，理论可照搬）；B 箱 = `_name` + 同名 `_inherit` 的重声明（`account.bank.statement.line`、`hr.employee`、`hr.expense`、`res.partner`、`res.company`、`account.journal`，另发现 `tour_guide_portal/models/hr_expense.py` 同样模式）。
2. **B 箱逐模型 `fields_get` diff**：凡重声明了上游已有字段的定义 → **一律删，降级为纯 `_inherit` 只留增量字段**；行为覆盖（compute/onchange/constraint）逐个在 20 语义下人工复核（如 statement line 的 `account_id` 已是 related 概念，旧 Many2one 必错）。
3. **报表层必须保**（20 社区无原生总账/余额，砍=砍业务）：先试装自包含向导层；不行再评估 OCA 20 版。唯一必改：`report.account.report_invoice` 覆写需对齐 20 的 `account.move.send._get_default_pdf_report_id` 渲染入口。
4. 46 处裸 SQL 按 diff 报告逐个复核；`tour_website_sale` JS 重写为 OWL。
5. **tour_saas 本期停用**（20 无运行时建库 API；全仓无模块依赖它；租户表仅 1 行"测试旅行社"）。需要保留"暂停服务"产品能力的话，改成约 80 行薄模块、不带建库线程；"多租户 SaaS 化"正式移出本期范围 → 写进 b-蓝图 范围变更。

**Gate B1**：20 空库 `-i` 全绿（tour_* 21 个，去掉 tour_saas）+ tour_accounting 14 项单测通过 + 自建对账 case（凭证/核销/银行对账）通过。

## 8. Phase B2 — 迁移管线 + dry-run（15–25 人日）

纯逐模型 ORM ETL 对 82 万行账本不现实（1–3k 行/分钟 → 全量 3–7 天）且不完整（`matching_number == str(full_reconcile_id.id)`、`account.partial.reconcile` 的 `last_debit/credit_move_id` 去重约束会违约）。**采用分象限混合管线**：

| 象限 | 内容 | 手法 |
|---|---|---|
| 1 不可变历史 | `account_move` / `account_move_line` / `account_partial_reconcile` / m2m `account_move_line_partial_rel` / 已过账凭证的 `ir_attachment` 元数据 | staging 表转换列后整表 INSERT **保留原 ID** + `setval` 序列 + 拷 `ir_model_data`（保 XMLID、带 noupdate）。保留 ID 使 `matching_number` 约束自动成立 |
| 2 活跃/强业务逻辑 | 未核销残差行、partner/bank、product、tour_* 51 表、sale/purchase 头 | `odoo-bin shell` 走 `create()`（吃 compute/constraint 钩子），按 `ir_model_data` 拓扑定序，分批 + 批间 commit |
| 3 配置/元数据 | `ir_sequence`（含 next_number 状态）、`ir.cron`、`ir.property`、`mail.template`、`res_users`（密码哈希直拷）、`res.company`（锁日期） | SQL 直拷 + 复核 |
| 附件 | 19/20 均无 `db_id` 列，`store_fname` 相对库名 filestore | filestore `rsync -a` 直拷 + `ir_attachment` 走象限 1 |

每象限出对账报告，核对不变式：① 每账户借贷合计相等；② 每个 partial 的 `amount_type/amount` 与两侧残差回算一致；③ 每 move `amount_total` 抽 1% 重算；④ m2m 行数双侧一致；⑤ `matching_number` 全量重跑 20 约束；⑥ 单公司（已核实 companies=1）可省多公司象限，但 `account.journal` 默认账户列需先 diff。

交付：`scripts/migration/` 的 etl_extract / etl_load / recon 三件套 + 每模型映射 yaml + **迁移台账** `MIGRATION_LEDGER.md`（批次号 | 时间 | 源/目标 DB + schema version/commit | 模型/表 | 象限 | 预期/实际行数 | 金额或校验和判据 | XMLID 映射版本 | 执行人/工具版本 | 结果与差异链接 | 回滚点 | 状态）。

**Gate B2**：**完整 dry-run ≥ 2 次且两次零对账差异**；单次总耗时 ≤ 可谈判窗口（目标 < 6 h）；`tour20.solepro.cloud` UAT 通过。

## 9. Phase B3 — 切换与灰度（5–8 人日）

冻结（旧库 PG 级只读：`ALTER DATABASE ... SET default_transaction_read_only=on` + `ir_cron active=false`）→ 末次 dump → ETL → 对账 → `tour.solepro.cloud` upstream 改指 20 → 冒烟。`tms.solepro.cloud` 保留 19 只读回退，期间增量业务需有补录预案。

**切换后必做清单**：`web.base.url`（现为 `https://tms.solepro.cloud`）/ `web.database.external` 改 tour；**SMTP 实配 + 实测**（现网 `ir_mail_server` 计数为 0 → 密码重置和门户通知一直是坏的）；`res_company.fiscalyear_lock_date` 设锁；`ir.sequence` 前缀与 next_number 复核；`ir_model_data.noupdate` 标记保留；restrict_mode journal 的哈希链重建；若存在 OAuth provider 需按新域名重登记 redirect URI。
**Gate B3 / 发布判据**：对账 0 差异 + 冒烟 + 邮件实测；回退判据（触发条件 + 动作）事先评审签字。
**回滚**：nginx 回指 19 只读实例。

## 10. 交付物与目录（对齐仓库 a/b/c/d 约定，并同步更新 INDEX.md）

- `b-蓝图/技术设计/TDS-30-迁移架构与ETL设计.md`（含模块处置矩阵）、`TDS-31-回退预案.md`；tour_saas 多租户移出本期范围的范围变更说明。
- `c-系统实现/tour-platform/`（新 compose 项目 + `ODOO_PIN` 记录 20 commit SHA 与镜像 digest）、`c-系统实现/tms-platform/scripts/migration/`、`MIGRATION_LEDGER.md`。
- `d-交付验收/`：A1 一致性核对报告、A2 回归记录、B0 spike 报告、B2 两次 dry-run 耗时报告、**切换 runbook**（步骤号 | 命令 | 责任人 | 预期耗时 | 验证命令 | 成功判据 | 中止判据 | 回滚动作 | 实际耗时）、发布说明、已知问题清单、UAT 报告。
- alpha 可复现策略：现在 `git tag tms-20.1a1-r1 <SHA>` pin 住，B 阶段全程不动；每 2–4 周用新 worktree 检 master 头跑一次"空库全模块 `-i` + 单测 + 金样例对账"作金丝雀报告；**只有**上游修了我们被阻塞的 bug 或发布 20.x 正式版才前移基线，且前移 = 全量重验。最终目标写死为"上游 20.x 正式版"。

## 11. 工作量与主要不确定性

合计约 **67–113 人日 ≈ 2–4 个月**（A0 4–7 ｜ A1 5–8 ｜ A2 3–5 ｜ B0 5–10 ｜ B1 30–60 ｜ B2 15–25 ｜ B3 5–8）。
风险源排序：① 无 OpenUpgrade 20 参照，所有字段语义变更靠人工 diff（B0 是降险关键）；② Webkul OHRMS 14 件在 20 的可装性；③ 20 master 在 B 阶段期间 accounting 的变动速度；④ 切换窗口能否拿到 6–8 小时；⑤ 现网只有 17 个单测，UAT 清单必须人工编制。

## 12. 验证方式（怎么算成功）

- A0：恢复演练产物 + 登录/暴露面实测（`curl -k https://tms.solepro.cloud/web/database/manager` 应 404/403）。
- A1：对账脚本输出 0 差异；`tour.solepro.cloud` 登录后 tour_accounting 总账/余额表出数与 19 逐单元格一致。
- B1：20 空库 `-i` 全绿 + 单测通过（`--test-enable --test-tags`）。
- B2：两次完整 dry-run 的对账报告与耗时表；`tour20` UAT 签字。
- B3：切换后 20 实例对账 0 差异、邮件实测收到、回退路径演练过一次（演练时先回切再切回）。

## 13. 执行顺序建议（goal 落地）

Goal 按 A0 → A1 → A2 → B0 → B1 → B2 → B3 逐 gate 推进，每个 gate 完成后停下来汇报并等确认再进下一阶段；**A0 的三件事今天就能做且不阻塞**：备份恢复演练、20 dev 实例从 tour 收回、加密密钥来源审计。B1 之后若 gate 不过，允许把终态降级为"tour = 19 标准化生产，20 停留在 tour20 预发"，并把它记为已知问题。
