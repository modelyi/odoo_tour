# TDS-31 回退预案（A1 平桥切换 / B3 生产切换）

- 版本：v0.1（2026-09-21）
- 上游：`迁移与升级计划-TMS到tour.md` §4（A1）、§9（B3）、§12（回退路径须演练一次）
- 责任人栏为**角色**，实际签字人须在切换评审会上落成姓名与时刻。

## 0. 三条不变式（任何回退动作都不得违反）

1. **域名动作只有一件事**：改 nginx upstream 指向 + `nginx -t` + `reload`。
   回退时同样只改这一处，**绝不夹带**配置变更、模块升级、数据修补。
2. **旧系统只冻结不销毁**：切换后 `tms`（19）至少保留 30 天，且切回前必须先解除只读；
   任何回退都不需要"重建"旧环境，只需要"解除冻结 + 改指向"。
3. **回退是被计划的成功路径**，不是事故：触发判据命中即执行，不允许"再观察十分钟"。
   观察窗口每次 ≤ 5 分钟，由现场指挥（值班负责人）单方面决定回退。

## 1. 现网拓扑事实（回退动作的作用域）

| 对象 | 实测值 | 出处 |
|---|---|---|
| `tms.solepro.cloud` | `/etc/nginx/conf.d/solepro.cloud.conf`：`location /`→`upstream tms_frontend`(127.0.0.1:8070)、`/longpolling`+`/websocket`→`tms_longpolling`(8073) | 本次实测 |
| `tms-odoo` 容器 | 发布 `127.0.0.1:8070->8069`、`8073->8072`；库 `tms`；镜像 id `9ebb8c2d5340` | `docker ps` |
| `tour.solepro.cloud`（当前） | `/etc/nginx/conf.d/tour.solepro.cloud.conf:72,77` → `return 503`（A0-4 收回的占位页）；`:82` 有注释掉的 `proxy_pass http://odoo20_app` | 本次实测 |
| 19 平桥实例 | `tour-odoo` → `127.0.0.1:8071->8069`，库 `tour19`，`dbfilter=^tour19$`；`tour-staging.solepro.cloud.conf` 的 `upstream tour_odoo_a1`(8071) 已在验收用 | A1 报告 §1 |
| 20 dev 实例 | `127.0.0.1:28069`（源码 `/home/adai/odoo20`）+ `odoo20-db:5434` | A0-4 |

> **A1 切换前必须做的编辑**：`tour.solepro.cloud.conf` 注释里的目标是 `odoo20_app`(28069)，
> A1 要指向 `tour_odoo_a1`(8071)。做法：在 `server 443` 块内新增
> `upstream tour_odoo_a1 { server 127.0.0.1:8071; }`（与 staging vhost 同名 upstream 会被 nginx
> 判为重复定义 → **改用不同名** `tour_odoo_main`），把 `/`、`/longpolling`、`/websocket`
> 三处 `return 503` 换成 `proxy_pass`。这是**一次成型的 4 行改动**，改完 `nginx -t` 必须通过。

## 2. 回退点 R-A1：19 平桥切换（tour → 8071）之后

### 2.1 触发判据（命中任一即回退，无需讨论）

| # | 判据 | 阈值 | 怎么测 |
|---|---|---|---|
| T1 | 登录不可用 | 连续 3 次（不同账号）失败，或 `/web/login` 非 200 | `curl -si -k https://tour.solepro.cloud/web/login`；A1 报告 §5 的表单字段是 `password` |
| T2 | 总账/余额表出数偏差 | 与 19 任一格不等 | 跑 `scripts/migration/a1_golden_paths.py`（G1），比对 `G1.digest`/`G1.total_debit` |
| T3 | 附件不可读 | 任一抽样 404/500 | G4：`G4.sha1_mismatch>0` 视为硬故障；`G4.missing` 与 19 同值不算故障 |
| T4 | 写入链路报错 | 过账/核销任一断言 False | G2（`RUN_WRITE=1`，跑在 tour19 上，脚本自带 rollback） |
| T5 | 5xx 或连接池耗尽 | 5 分钟窗口 5xx > 1%，或 `FATAL: too many connections` | `grep -c ' 5[0-9][0-9] ' ` 容器日志 + `pg_stat_activity` 计数 |
| T6 | 模块未加载（隐性） | registry 模型数 ≠ 19 侧 | `curl /web/webclient/load_menus` 后核 `ir_model` 计数；A1 已证两侧同为 758 → 不等即回退（见 K13） |

### 2.2 回退动作（≤ 60 秒，可完全撤销）

```bash
sudo cp /etc/nginx/conf.d/tour.solepro.cloud.conf \
        /etc/nginx/conf.d/tour.solepro.cloud.conf.bak.a1-rollback.$(date +%s)
sudo sed -i -E 's|^(\s*)proxy_pass http://tour_odoo_main;|\1return 503;|' \
     /etc/nginx/conf.d/tour.solepro.cloud.conf          # 或直接用备份的 park 版覆盖
sudo nginx -t && sudo nginx -s reload
curl -s -o /dev/null -w '%{http_code}\n' -k https://tour.solepro.cloud/web/login   # 期望 503
```

- `tms.solepro.cloud` 全程未动 → 回退后**用户无感**，旧入口继续可用。
- 平桥实例（`tour-odoo`）**保留运行**用于事后取证，不要在回退当口 `docker compose down`。
- 台账：`c-系统实现/tms-platform/scripts/migration/MIGRATION_LEDGER.md` 追加一行，
  记 `A1-rollback`、触发判据编号、时刻、执行人、`nginx -t` 结果。

## 3. 回退点 R-B3：20 生产切换之后（风险最高，预案必须最厚）

### 3.1 触发判据

| # | 判据 | 阈值 |
|---|---|---|
| U1 | 对账非 0 差异（切换后复算） | 任一表行数差 ≠ 0 或 `sum(debit)≠sum(credit)` |
| U2 | 财务出数与 19 只读实例不等 | 逐户比对 3 个账户抽验 |
| U3 | 权限越权或门户空白 | A1 §5 权限矩阵任一格翻转（20 的 `ir.access` 转换出错，见 TDS-30 §3-F2） |
| U4 | 附件批量 404 | > 0.5% 抽样失败 |
| U5 | 邮件仍不可发 | B3 清单里的 SMTP 实测未通过（K10） |
| U6 | 业务中断 | 导游门户下单/排团任一金样例链路失败，且 30 分钟内无法定位 |

### 3.2 回退动作

```bash
# 1) 域名回指 19（只改 upstream）
sudo vi /etc/nginx/conf.d/tour.solepro.cloud.conf     # proxy_pass → 19 实例（tms_frontend/8070 或平桥 8071）
sudo nginx -t && sudo nginx -s reload
# 2) 解除 19 的只读冻结（B3 冻结命令的逆操作）
docker exec tms-db psql -U odoo -d postgres -c \
  "ALTER DATABASE tms SET default_transaction_read_only = off"
# 3) 恢复 cron：按 B3 冻结前**逐行记录**的 ir_cron.id 清单回填 active=true（不许全量置真）
# 4) 停 20 实例但保留其库（取证 + 补录数据源）
docker compose -f .../tour20/docker-compose.yml stop odoo
```

**硬性前置**：B3 冻结前必须把 ① `select id,active from ir_cron where active` 落盘、
② 冻结时刻 `tms` 的最大 `write_date`/各表 `last_value` 记入台账。
缺任一条 → **禁止执行 B3 切换**（回退后无法安全恢复 cron，会造成重复开票/重复付款）。

### 3.3 回退期间的增量补录（20 上产生、19 上没有的数据）

按窗口补录，不允许手工重录（人工重录财务凭证不可审计）：

1. 冻结 20 写入（同 §3.2 的 PG 只读手法）。
2. 取窗口：`W0 = B3 切换时刻`，`W1 = 回退时刻`。
3. 导出增量：对**tour_\* + account_* + res_partner + product_*** 逐表
   `where write_date > W0` → CSV + 关联 `ir_attachment` 及其 filestore 文件。
4. 人工核对条数与金额合计后，在 19 上以**业务操作**重放（走 ORM，不直插 SQL），
   保证 compute/序列/核销链在 19 侧自洽。
5. 补录完成后把 20 实例标记为"已封存"，并在发布说明的已知问题清单里记窗口与条数。

> 若窗口内增量 > 50 张凭证或含已过账凭证的重开，**默认决策改为**：不回退，
> 在 20 上前向修复（hotfix），因为补录的风险已高于故障本身。该决策由 Owner 签字。

## 4. 冻结与解冻（两个回退点共用的动作语义）

```sql
-- 冻结（切换前）
UPDATE ir_cron SET active = false WHERE active = true;   -- 先落盘原清单再执行
ALTER DATABASE tms SET default_transaction_read_only = on;
-- 解冻
ALTER DATABASE tms SET default_transaction_read_only = off;  -- 或 RESET
```

- 连接已有会话不受 `ALTER DATABASE ... SET` 影响 → 冻结前必须
  `select count(*) from pg_stat_activity where datname='tms' and state <> 'idle'` 为 0，
  或显式 `SELECT pg_terminate_backend(pid)`（属破坏性动作，须现场指挥授权）。
- 解冻后**核对 cron**：只允许恢复原清单内的 id，其余保持 false（A1 期发现的
  tour_accounting recurring invoice/payments 双跑风险，见计划 §4 第 1 步）。

## 5. 备份与恢复锚点（回退的最后手段）

| 锚点 | 位置 | 恢复方式 |
|---|---|---|
| 每次切换前的 `tms` dump | `backup.sh` 产物 `*.dump.gz`（pg_dump -Fc + gzip，双库 + filestore tar） | `gunzip -c X.dump.gz \| docker exec -i tms-db pg_restore -U odoo -d <新库> --no-owner` |
| filestore | `.../filestore/*.tar`（`--numeric-owner`） | 解 tar 后 `chown -R 100:101`，**目录名必须等于目标库名** |
| 已演练过的证据 | `d-交付验收/A0-备份恢复演练_20260921_060048.md`（910 指纹键 0 差异） | 恢复演练即"回退到最后一次已知good"的可行性证明 |

A0 的结论仍然有效：**没有当日备份就没有切换资格**。B3 切换当日必须重跑一次恢复演练，
产物名与哈希进台账，才算拿到回退锚点。

## 6. 演练要求（计划 §12 的硬判据）

切换日前必须做一次**完整演练**，且演练本身就是回退：

1. 在 staging（`tour-staging.solepro.cloud`，DNS 待补，K6）用真实 dump 拉起 20；
2. 执行 §3.2 的回退动作 → 验证 19 可写、cron 正常触发一次；
3. 再切回 20；
4. 记时：冻结→dump→ETL→对账→回退→再切换，全链路耗时表进
   `d-交付验收/切换runbook`，用于校准计划 §8 的"< 6 h"窗口承诺。

演练未做 → **不允许排期 B3**。

## 7. 待补

| 项 | 说明 |
|---|---|
| 现场指挥与副手姓名/联系方式 | 切换评审会填 |
| `tour.solepro.cloud` 的 A1 版 vhost 全文 | 需授权后生成并 `nginx -t` 预演（本预案 §1 注） |
| 补录脚本 | `scripts/migration/` 下待写 `b3_delta_export.py`（§3.3 第 3 步） |
| cron 原清单落盘格式 | 建议 `csv: id,active`，文件名含冻结时刻与库名，进台账 |
