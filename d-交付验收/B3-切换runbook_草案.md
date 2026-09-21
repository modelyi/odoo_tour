# B3 切换 Runbook（19 平桥 → 20 新生产）— 草案 v1

> 状态：**草案，未演练**。生效前置：B1 全模块 `-i` 通过 + B2 两次完整 dry-run 零对账差异 +
> 本 runbook 走过一次「回滚演练」（步骤 12）。任何一步命中「中止判据」即停，不猜、不跳步。

## 0. 不变式与拓扑（切换前后）

| 域名 | 切换前 | 切换后 | nginx 事实 |
|---|---|---|---|
| `tour.solepro.cloud` | 503（A0-4 已收回） | **20 新生产** | `/etc/nginx/conf.d/tour.solepro.cloud.conf`，被注释的 `proxy_pass http://odoo20_app` 段 |
| `tour-staging.solepro.cloud` | 19 平桥（A1） | 停用 | upstream `tour_odoo_a1` → `127.0.0.1:8071` |
| `tms.solepro.cloud` | 19 生产 | 19 **只读回退** | `solepro.cloud.conf` 内 upstream `tms_frontend` → `127.0.0.1:8070`（长连接 `tms_longpolling` → 8073） |
| 20 实例 | 源码 `127.0.0.1:28069`（`/home/adai/odoo20`） | 20 生产载体（改 `dbfilter`/`http_port` 后同端口） | 容器化与否在 B1 定稿；本 runbook 假定仍为本机 systemd/进程 + 独立 DB `tour20` |

单域名 ↔ 单实例；域名动作**只改 upstream + reload**，不夹带任何配置/数据变更。

## 1. 主流程

| # | 动作 / 命令 | 责任人 | 预期 | 验证命令 | 成功判据 | 中止判据 | 回滚动作 | 实际耗时 |
|---|---|---|---|---|---|---|---|---|
| 0 | 冻结窗口对外公告（提前 ≥ 48 h）；确认窗口 ≥ 8 h；确认当日备份已通过恢复演练 | 负责人 | 30 min | 邮件/群公告 + `ls -l /home/adai/backup/tms-*.dump.gz` | 有回执；备份文件存在且演练报告为「通过」 | 无人确认窗口 | 无需 | |
| 1 | 停写入：`docker exec tms-odoo python -c` 或直接 `UPDATE ir_cron SET active=false WHERE active` **先把命中的 id 列表存进台账** | 运维 | 10 min | `SELECT count(*) FROM ir_cron WHERE active;` → 0 | 计数归零且 id 清单入库 | 有活动事务无法收敛 | `UPDATE ir_cron SET active=true WHERE id = ANY(清单)` | |
| 2 | 旧库 PG 级只读：`ALTER DATABASE tms SET default_transaction_read_only = on;` | 运维 | 2 min | `SELECT current_setting('default_transaction_read_only');` | on | 连接池不生效 | `ALTER DATABASE tms RESET default_transaction_read_only;` | |
| 3 | 站点维护页：`tour.solepro.cloud` location `/` 置 503 + `proxy_intercept_errors`（若已 503 则跳过） | 运维 | 3 min | `curl -sI https://tour.solepro.cloud/web | head -1` | 503 | — | 还原 conf | |
| 4 | 末次导出：`docker exec tms-db pg_dump -Fc -f /tmp/tms_final.dump tms` → 落盘并 `sha256sum` 进台账；`rsync -a` filestore | 运维 | 25–40 min | `pg_restore --list /tmp/tms_final.dump | head` | 清单可读、大小与 2.6 GB 同量级；哈希一致 | dump 报错或体积异常 | 取消切换（此时尚未破坏性写入） | |
| 5 | 重建目标库：`createdb tour20` → `pg_restore -d tour20 --no-owner --role=odoo /tmp/tms_final.dump`（或跑 B2 ETL 三件套） | 运维 | 40–90 min | `psql -d tour20 -c "select count(*) from account_move_line;"` | 行数 = 源库行数 | restore/ETL 任一象限报错 | dropdb tour20（仅目标库） | |
| 6 | filestore 落位：目录名必须等于目标库名，属主 uid 与 20 进程一致 | 运维 | 15 min | `find <filestore>/tour20 -type f | wc -l` ≈ `SELECT count(*) FROM ir_attachment WHERE store_fname IS NOT NULL;` | 差 ≤ 0（缺失记 0） | 差异 > 0 | 重拷 | |
| 7 | 模块升级：`odoo-bin -c odoo.conf -d tour20 -i <tour_*+OHRMS 清单> -u all --stop-after-init`（20 侧 `ir.access`/`tour.bank` 改造版） | 开发 | 20–40 min | 退出码 0 + 日志无 `ERROR` | 全绿 | 任何 ImportError/字段缺失 | 回到步骤 5（不碰 19） | |
| 8 | **对账**：`scripts/migration/recon.sh` + B2 的 6 条不变式 + `security` 权限矩阵（A1 报告 §5） | 测试 | 20 min | 对账报告 | **0 差异** | 任何一项非 0 | 回到步骤 5 | |
| 9 | 切换后配置清单（见 §2） | 运维 | 15 min | 见 §2 逐条 | 逐条通过 | 邮件/域名不通 | 改回 §2 各项 | |
| 10 | 域名切换：`tour.solepro.cloud.conf` 的 `location /` 换成 `proxy_pass http://odoo20_app;`（含 longpolling 段）→ `nginx -t && nginx -s reload` | 运维 | **≤ 2 min** | `nginx -t`；`curl -sI https://tour.solepro.cloud/web/login` | 200 + HTML 含 20 版本号 | `nginx -t` 失败 | 还原一行 conf + reload（秒级） | |
| 11 | 冒烟（G1–G5 金样例：登录/权限、财务过账+核销、导游门户、报表逐单元格、附件下载） | 测试 | 30 min | `scripts/migration/a1_golden_paths.py` | 全部通过 | 任一链路失败 | 步骤 12 | |
| 12 | **回滚演练**（正式切换前在 staging 上先做一次）：切回 19 → 验证可读 → 再切 20 | 运维+测试 | 40 min | `git log` 台账 + 冒烟 | 双向切换各成功一次 | 回滚后 19 不可用 | 立即人工介入 | |
| 13 | 台账收尾：`MIGRATION_LEDGER.md` 记批次号/源与目标 schema version/对账结果/回滚点；发布说明 + 已知问题清单 | 负责人 | 20 min | — | 台账完整 | — | — | |

## 2. 步骤 9 的必做配置（B3 切换后清单）

| 项 | 动作 | 验证 |
|---|---|---|
| `web.base.url` | 现值 `https://tms.solepro.cloud` → `https://tour.solepro.cloud` | 门户邮件内链接指向 tour |
| `web.database.external` | true | 后台 URL 无端口 |
| SMTP | **现网 `ir_mail_server` 计数为 0（K10，密码重置一直是坏的）** → 实配并**实测发信收信** | 真收到一封重置邮件 |
| 加密密钥 | `TMS_FIELD_ENCRYPT_KEY` 与 A0-2 的密文列清单一致，密文字段可读回 | 抽样解密成功 |
| `res.company.fiscalyear_lock_date` / `taxes_lock_date` | 按财务定的锁日期设置 | 过账被拒 |
| `ir.sequence` | 前缀与 `next_number` 复核（尤其 A1 期间是否有并发取号） | 下一张凭证号无重号/跳号 |
| `ir_model_data.noupdate` | 标记保留，防止 `-u all` 覆盖客户改过的数据 | `select count(*) from ir_model_data where noupdate;` 与源一致 |
| restrict_mode journal | 20 社区版带 `inalterable_hash` 校验 → 迁移后**重建哈希链**，否则新过账报错 | 试过账一张凭证 |
| OAuth provider | 若有，redirect URI 按新域名重登记 | 第三方登录成功 |
| `tms` 回退库 | 保持只读 + `ir_cron` 关闭，至少留 30 天；期间增量业务走「补录预案」 | 只读生效 |
| 19 侧 `ir_cron` | **不要在 19 恢复启用**（双跑） | `select count(*) from ir_cron where active;` = 0 |

## 3. 回退判据（触发即回滚，不现场调试超过 15 min）

1. 步骤 8 对账出现任何非 0 差异且 15 min 内无法定位；
2. 步骤 11 金样例任一链路失败（财务不能过账 / 门户看不到单据 / 附件 500）；
3. 步骤 9 邮件实测发不出去且影响业务通知；
4. 切换后 30 min 内出现 5xx 比率 > 1% 或响应 P95 相较 19 基线劣化 > 2×；
5. 财务在首日核对中发现报表出数与 19 不一致（逐单元格判据）。

**回滚动作**：`tour.solepro.cloud` conf 还原为 503/或指回 `tour_odoo_a1`（19 平桥）→ reload（秒级）；
`tms.solepro.cloud` 解除只读 + 恢复 §1-1 记录的 cron id → 冒烟；20 侧数据保留现场供事后定位，
期间增量按 §2 补录预案回写 19。回滚不需二次授权（本 runbook 评审时一并签字）。

## 4. 时间线与决策点

冻结(T+0) → 导出/restore/filestore(T+1:30) → 模块升级(T+2:10) → 对账(T+2:30) →
**GO/NO-GO 决策点（负责人 + 财务 + 测试三方签字，T+2:45）** → 域名切换(T+3:00) →
冒烟(T+3:30) → 值守观察 60 min(T+4:30) → 宣布完成。整体目标 ≤ 6 h，窗口预留 8 h。
