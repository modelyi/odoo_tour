# ODOO_PIN —— odootour 版本固定记录

约定与 tms-platform/tour-platform 的 A0-5 一致：**一切镜像按 digest 固定，升级必须显式换 pin 并走一遍冒烟。**

## 当前 pin（2026-09-25 装机）

| 项 | 值 |
|----|----|
| 来源 | https://github.com/odoo/odoo（社区版，零 patch） |
| 分支 | `20.0` |
| commit | `87a1773bda6c87bd4a1fc276bbe4bc8fe8f81a11` |
| 构建方式 | 自建镜像 `Dockerfile.odoo`（Docker Hub 无官方 odoo:20 镜像，2026-09-25 用 registry API 核实；最新为 19.0-20260908） |
| 基础镜像 | `python:3.12.14-bookworm` @ `sha256:dbbe4ceb97851e2e5fa83798b239811f871cb743b259ba3563737349f6bcfaa0` |
| 数据库 | `postgres:16-alpine` @ `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| 镜像产物 | `odootour:20.0-a1` = image ID `d1966975a5fb`（本地 build 无 push digest，按 image ID 固定） |
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
