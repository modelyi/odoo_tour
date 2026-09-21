# MIGRATION_LEDGER — 迁移台账

计划依据：`lone-quarry-colt` §8。每一次"灌数据/改结构"的批动作都必须在此登记一行，**含失败与回滚**。
判据列写"可复核的数值"，不写"看起来正常"。

| 批次 | 时间(UTC) | 源 → 目标 | 范围 | 象限 | 预期/实际 | 判据 | XMLID/工具版本 | 执行人 | 结果 | 回滚点 | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1-01 | 2026-09-21 06:0x | `tms` @dump `tms__20260921_055910.dump.gz`(101,366,000 B, sha256 `182af8de9b84ab1f…`) → `tour19` | 全库 891 表 | 整库复制 | 891 / 891 表；行数逐表一致 | `recon.sh` 910 键，差异仅 `ir_cron_progress 1935→1933`（易变） | `pg_restore --no-owner --role=odoo`，镜像 `9ebb8c2d5340` | Qoder(A1) | PASS | `dropdb tour19` 即回到空实例 | 已核 |
| A1-02 | 2026-09-21 06:0x | `filestore/tms` → `filestore/tour19` | 附件二进制 | 附件直拷 | 2,785 / 2,785（rsync 后测得 2,787，+2 属 A1-04 冒烟） | 抽样 sha1 自校验 48/48 命中、0 不匹配（`a1_golden_paths.py` G4） | `rsync -a` 保属主 `100:101` | Qoder(A1) | PASS | 删 `filestore/tour19` | 已核 |
| A1-03 | 2026-09-21 07:1x | 只读冒烟：`tms` vs `tour19` | G1 总账 + G3 门户 + G4 附件 + G5 权限 | 校验（无写入） | 27 键 / 27 键一致 | G1 `lines=15,059` `lines_digest=0632622847c7a337` 两侧同值；借=贷=`489,440,567.54` | `a1_golden_paths.py` RUN_WRITE=0 | Qoder(A1) | PASS | 无需（只读） | 已核 |
| A1-04 | 2026-09-21 07:2x | `tour19` 内写入后回滚 + 2 个探针用户 | G2 过账+核销；`a1_smoke_internal/portal` | 校验（含写入） | `posted=True` 4 项不变式 True，`rolled_back=True` | G2 全绿；残留 `res_users+2`、`ir_attachment+20`(id≥28462)、filestore+2 | 同上 RUN_WRITE=1；探针用户 `unlink` 受阻于 `hr_employee_user_id_fkey`（K12） | Qoder(A1) | PASS(带残留) | 由 A1-05 末次灌库覆盖 | **待清** |
| A1-05 | 计划中 | `tms` 末次 `pg_dump -Fc` → `tour19` 重灌 | 全库 | 整库复制 | 待测 | recon 910 键 **0 差异**（含 `ir_cron_progress`，因冻结后 cron 不再跑） | 冻结后 `ir_cron.active` 原值先导出留档 | 待授权 | — | nginx upstream 回切 tms（秒级） | **未开始（需授权）** |

## 登记规则

1. 一行 = 一个可独立回滚的批动作；失败也要登记（结果列写 `FAIL` + 差异链接）；
2. "判据"必须是**可复跑的数值**：`bash scripts/migration/recon.sh <db容器> <库名>` 或 `a1_golden_paths.py` 的键；
3. 象限含义见计划 §8：1 不可变历史（SQL 保 ID）/ 2 活跃强逻辑（ORM create）/ 3 配置元数据（SQL 直拷+复核）/ 附件（filestore 直拷）；
4. B2 起每行还要记 ETL 脚本的 git commit（工具版本列）。

## 待办挂账（本文件之外的未关闭项）

- K1 凭据外泄远端分支处置：**待授权**；
- K6 `tour-staging` / `tour20` DNS 记录：待用户在 Cloudflare 添加；
- A1-05 冻结+末次灌库+域名切换：待授权（生产可见）。
