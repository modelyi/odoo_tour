# TMS 旅行社管理系统 — 项目总目录

> 更新日期：2026-09-12  
> 项目阶段：调研完成 → 蓝图设计中  
> 技术栈：Odoo 19 + PostgreSQL 16 + Redis 7 + Docker + Nginx

---

## 项目结构

```
tms/
├── INDEX.md                           ← 本文件（项目总目录）
├── AGENTS.md                          项目协作规范
├── README.md                          项目简介
│
├── a-调研/                            阶段1：调研分析 ✅
├── b-蓝图/                            阶段2：规划设计 🔧 进行中
├── c-系统实现/                        阶段3：开发实现 ⏳ 待启动
└── d-交付验收/                        阶段4：交付验收 ⏳ 待启动
```

---

## P. 项目与产品管理

> 项目管理类文档，跟踪进度、风险和决策。

| 文档 | 状态 | 说明 |
|------|------|------|
| [文档体系规划.md](b-蓝图/文档体系规划.md) | ✅ 完成 | 53份文档清单、优先级、负责人 |
| [产品路线图.md](b-蓝图/产品设计/产品路线图.md) | ✅ 完成 | Phase 1-5 演进路线、里程碑 |
| [功能优先级矩阵.md](b-蓝图/产品设计/功能优先级矩阵.md) | ✅ 完成 | 135项功能 P0-P3 分级 |
| 项目计划.md | ⏳ 待编写 | Sprint计划、里程碑时间表 |
| 迭代计划.md | ⏳ 待编写 | 当前Sprint目标和任务 |
| 风险登记册.md | ⏳ 待编写 | 风险识别、评估、缓解措施 |
| 决策日志.md | ⏳ 待编写 | 重要决策记录和理由 |

---

## A. 调研分析 ✅

> 易途 V7 系统全量数据采集与业务分析（2026-09-12 完成）。

| 文档 | 大小 | 说明 |
|------|------|------|
| [调研数据说明.md](a-调研/调研数据说明.md) | 8.4 KB | 27张表/180,076条记录采集说明 |
| [易途系统功能调研.md](a-调研/易途系统功能调研.md) | 21 KB | 247项菜单、12种业务模式、7个子产品 |
| [易途系统表单字段文档.md](a-调研/易途系统表单字段文档.md) | 51.9 KB | 27张表完整字段定义（1,032个字段） |
| [Odoo功能映射方案.md](a-调研/Odoo功能映射方案.md) | 9.5 KB | 易途→Odoo 19 模块/模型映射 |
| [需求文档.md](a-调研/需求文档.md) | 2.6 KB | TMS 核心需求（6大模块） |
| [spa.html](a-调研/spa.html) | 6.1 MB | 调研报告可视化（含截图+桑基图+ER图） |

### 数据资产

| 资产 | 位置 | 说明 |
|------|------|------|
| 易途系统数据.db | a-调研/ | SQLite 全量数据库（374 MB） |
| et_data/ | a-调研/et_data/ | 28对 CSV+JSON 文件（316 MB） |
| screenshots/ | a-调研/screenshots/ | 25张系统截图（1920×1080） |
| et_login.py | a-调研/ | 登录模块（可复用） |
| collect_data.py | a-调研/ | 数据采集脚本 |

---

## B. 蓝图设计 🔧

> 产品规格、业务规则、技术架构设计。

### B1. 产品设计

| 文档 | 大小 | 负责人 | 说明 |
|------|------|--------|------|
| [PRD-产品需求文档.md](b-蓝图/产品设计/PRD-产品需求文档.md) | 10.9 KB | product-manager | 产品愿景、8类角色、10大模块、成功指标 |
| [产品路线图.md](b-蓝图/产品设计/产品路线图.md) | 13.6 KB | product-manager | Phase 1-5 功能列表、里程碑、依赖 |
| [功能优先级矩阵.md](b-蓝图/产品设计/功能优先级矩阵.md) | 18.4 KB | product-manager | 135项功能 × 价值/成本 → P0-P3 |

### B2. 业务规格（旅行业务）

| 文档 | 大小 | 负责人 | 说明 |
|------|------|--------|------|
| [BS-01-线路管理.md](b-蓝图/业务规格/BS-01-线路管理.md) | 12.2 KB | tour-ba | 线路分类(85)、线路模板(212/82字段)、发团计划 |
| [BS-02-订单管理.md](b-蓝图/业务规格/BS-02-订单管理.md) | 17.1 KB | tour-ba | 团队订单(86,925/137字段)、报名(86,753/77字段)、并团 |
| [BS-03-计调操作.md](b-蓝图/业务规格/BS-03-计调操作.md) | 23.9 KB | tour-ba | 7大资源安排、9个数据模型、冲突检测 |
| BS-04-导游管理.md | ⏳ 待编写 | tour-ba | 导游档案(2,173/64字段)、派导、报账 |
| BS-09-购物管理.md | ⏳ 待编写 | tour-ba | 购物录入、统计、业绩分析 |
| BS-10-同业分销.md | ⏳ 待编写 | tour-ba | 同业价格、在线预订、结算 |
| BS-11-报表分析.md | ⏳ 待编写 | tour-ba | 40+报表、BI看板 |

### B3. 业务规格（财务管理）

| 文档 | 大小 | 负责人 | 说明 |
|------|------|--------|------|
| [BS-05-财务管理.md](b-蓝图/业务规格/BS-05-财务管理.md) | 15.6 KB | finance-ba | 18科目、单团核算、7结算方式、72银行账户 |
| [BS-06-收付款流程.md](b-蓝图/业务规格/BS-06-收付款流程.md) | 21.3 KB | finance-ba | 收款认领三步闭环、付款审批、导游借款 |
| [BS-07-对账结算.md](b-蓝图/业务规格/BS-07-对账结算.md) | 21.9 KB | finance-ba | 10类对账、签单月结、二次结算 |
| [BS-08-佣金计算.md](b-蓝图/业务规格/BS-08-佣金计算.md) | 25.9 KB | finance-ba | 多层分成、购物协议、人均线考核 |
| [BS-16-期初建账方案.md](b-蓝图/业务规格/BS-16-期初建账方案.md) | 15.0 KB | finance-ba | 补期初余额 + 修复总账三表仿真（opening entry） |
| [BS-19-单团毛利口径裁定与最小改造方案.md](b-蓝图/业务规格/BS-19-单团毛利口径裁定与最小改造方案.md) | 18.9 KB | finance-ba | 单团毛利口径裁定（差额征税/净额法）+ 台账字段最小改造 |

### B4. 技术设计

| 文档 | 大小 | 负责人 | 说明 |
|------|------|--------|------|
| [技术架构思路.md](b-蓝图/技术架构思路.md) | 26.1 KB | product-architect | 整体技术选型、SaaS、小程序、AI演进 |
| [TDS-系统架构设计.md](b-蓝图/技术设计/TDS-系统架构设计.md) | 17.0 KB | product-architect | 架构图、Docker编排、多租户、升级路径 |
| [TDS-数据模型设计.md](b-蓝图/技术设计/TDS-数据模型设计.md) | 39.8 KB | product-architect | 8个核心表字段映射、索引、分区方案 |
| [TDS-模块划分.md](b-蓝图/技术设计/TDS-模块划分.md) | 30.4 KB | product-architect | 14个模块、依赖关系、292人天工作量 |
| [TDS-缺口补齐方案与分阶段实施计划.md](b-蓝图/技术设计/TDS-缺口补齐方案与分阶段实施计划.md) | 22.6 KB | product-architect | 5类数据补缺 + 6项功能补齐 + 分阶段实施计划 |
| [迁移与升级计划-TMS到tour.md](b-蓝图/技术设计/迁移与升级计划-TMS到tour.md) | 16 KB | 批准版 | A0 基线加固 → A1 平桥 19 → A2 标准化 → B0–B3 升级 Odoo 20 并切换域名 |

### B5. 项目管理

| 文档 | 状态 | 负责人 | 说明 |
|------|------|--------|------|
| 项目计划.md | ⏳ 待编写 | product-manager | 总体时间表和资源分配 |
| 迭代计划.md | ⏳ 待编写 | product-manager | Sprint目标和任务看板 |
| 风险登记册.md | ⏳ 待编写 | product-manager | 风险识别和缓解措施 |

---

## C. 系统实现 ⏳

> Odoo 19 模块开发、部署配置。

### C1. 平台基础设施

| 文档/配置 | 状态 | 说明 |
|-----------|------|------|
| [tms-platform/README.md](c-系统实现/tms-platform/README.md) | ✅ 完成 | 平台说明、启动/部署指南 |
| [tms-platform/SUBAGENTS.md](c-系统实现/tms-platform/SUBAGENTS.md) | ✅ 完成 | 8个subagent角色说明 |
| docker-compose.yml | ✅ 运行中 | Odoo 19 + PG 16 + Redis 7 |
| config/odoo.conf | ✅ 配置完成 | Odoo 19 开发环境配置 |
| deploy.sh | ✅ 完成 | 自动化部署脚本 |
| Nginx 反代 | ✅ 运行中 | tms.solepro.cloud → 127.0.0.1:8070 |
| [tour-platform/](c-系统实现/tour-platform/) | 🚧 A1 平桥运行中 | 与 tms 同一镜像(`9ebb8c2d5340`)的 19 平桥实例：`tour-db/tour-odoo/tour-redis`，`127.0.0.1:8071`，库 `tour19`，`dbfilter=^tour19$`；pin 见 `config/ODOO_PIN.md` |
| [scripts/migration/](c-系统实现/tms-platform/scripts/migration/) | ✅ 完成 | `recon.sh`+`recon.sql`（910 指纹键核对）、`a1_golden_paths.py`（G1–G5 金样例）、`backup_restore_drill.sh`、`MIGRATION_LEDGER.md`（迁移台账） |

### C2. Subagent 角色配置

| 角色 | 文件 | 说明 |
|------|------|------|
| product-manager | [.subagents/product_manager.md](c-系统实现/tms-platform/.subagents/product_manager.md) | 产品规划、优先级 |
| product-architect | [.subagents/product_architect.md](c-系统实现/tms-platform/.subagents/product_architect.md) | 技术架构、模块设计 |
| tour-ba | [.subagents/tour_ba.md](c-系统实现/tms-platform/.subagents/tour_ba.md) | 旅行业务需求 |
| finance-ba | [.subagents/finance_ba.md](c-系统实现/tms-platform/.subagents/finance_ba.md) | 财务业务需求 |
| dev-odoo | [.subagents/dev_odoo.md](c-系统实现/tms-platform/.subagents/dev_odoo.md) | Odoo 模块开发 |
| devops | [.subagents/devops.md](c-系统实现/tms-platform/.subagents/devops.md) | 部署运维 |
| dev-qa | [.subagents/dev_qa.md](c-系统实现/tms-platform/.subagents/dev_qa.md) | 代码审查 |
| uat-qa | [.subagents/uat_qa.md](c-系统实现/tms-platform/.subagents/uat_qa.md) | 用户验收 |

### C3. Odoo 模块开发

| 模块 | 状态 | 说明 |
|------|------|------|
| tour_base | ✅ 已安装 | 线路分类、线路产品（基础模块） |
| tour_order | ⏳ 待开发 | 订单管理（依赖 BS-02） |
| tour_operation | ⏳ 待开发 | 计调操作（依赖 BS-03） |
| tour_guide | ⏳ 待开发 | 导游管理（依赖 BS-04） |
| tour_vehicle | ⏳ 待开发 | 车辆管理 |
| tour_supplier | ⏳ 待开发 | 供应商管理 |
| tour_shopping | ⏳ 待开发 | 购物管理（依赖 BS-09） |
| tour_finance | ⏳ 待开发 | 财务管理（依赖 BS-05~08） |
| tour_payment | ⏳ 待开发 | 收付款（依赖 BS-06） |
| tour_reconciliation | ⏳ 待开发 | 对账结算（依赖 BS-07） |
| tour_commission | ⏳ 待开发 | 佣金计算（依赖 BS-08） |
| tour_invoice | ⏳ 待开发 | 发票管理 |
| tour_report | ⏳ 待开发 | 报表分析 |
| tour_b2b | ⏳ 待开发 | 同业分销（依赖 BS-10） |

### C4. 开发文档

| 文档 | 状态 | 说明 |
|------|------|------|
| 开发规范.md | ⏳ 待编写 | Python/XML编码规范 |
| 模块开发指南.md | ⏳ 待编写 | 模块开发流程和模板 |
| 代码审查清单.md | ⏳ 待编写 | dev-qa 审查标准 |
| 数据库设计规范.md | ⏳ 待编写 | 表设计、索引、分区规范 |

---

## D. 交付验收 ⏳

> 测试、验收、上线。

| 文档 | 状态 | 说明 |
|------|------|------|
| [UAT测试报告_2026-09-12.md](d-交付验收/UAT测试报告_2026-09-12.md) | ✅ 完成 | 初次验收（10通过/5失败→已修复） |
| [A0-Gate基线加固报告_2026-09-21.md](d-交付验收/A0-Gate基线加固报告_2026-09-21.md) | ✅ 完成 | 迁移 A0 阶段 gate：备份/密钥/暴露面/镜像 pin + 已知问题清单 K1–K10（09-21 校订 2 处判据表述） |
| [A1-平桥验收报告_2026-09-21.md](d-交付验收/A1-平桥验收报告_2026-09-21.md) | 🚧 数据等价已实测通过 | 910 键核对 + G1–G5 金样例（总账 15,059 行摘要两侧同值）+ 登录/权限实测；**域名切换待授权**；新增 K11–K14 |
| [A0-备份恢复演练_20260921_060048.md](d-交付验收/A0-备份恢复演练_20260921_060048.md) | ✅ PASS | 910 指纹键 0 差异；filestore 备份缺陷 0（附 `A0-recon-*.tsv` 可复算） |
| 测试计划.md | ⏳ 待编写 | 测试策略和范围 |
| 测试用例库/ | ⏳ 待编写 | 按模块的测试用例 |
| 用户手册/ | ⏳ 待编写 | 管理员/操作员/财务员手册 |
| 最终验收报告.md | ⏳ 待编写 | 上线前最终验收 |

---

## 文档统计

| 阶段 | 已完成 | 待编写 | 总计 |
|------|--------|--------|------|
| A. 调研分析 | 6 | 0 | 6 |
| B. 蓝图设计 | 15 | 8 | 23 |
| C. 系统实现 | 11 | 4 | 16 |
| D. 交付验收 | 4 | 4 | 9 |
| P. 项目管理 | 3 | 4 | 7 |
| **合计** | **39** | **20** | **61** |

> 总计含 🚧 进行中行（A1 平桥报告、tour-platform 平桥实例），这两行不计入"已完成"。

### 文档体积

| 类别 | 大小 |
|------|------|
| 调研文档 | 83.4 KB + 6.1 MB(spa.html) + 690 MB(数据) |
| 蓝图文档 | 296.4 KB |
| 实现配置 | ~15 KB |
| **文本总计** | **~410 KB**（不含数据和截图） |

---

## 下一步行动

1. **B阶段收尾** — 编写剩余 P1 业务规格（BS-04/09/10/11）
2. **项目管理** — 编写项目计划、迭代计划
3. **C阶段启动** — tour_order 模块开发（基于 BS-02 规格）
4. **开发规范** — 编写开发规范和代码审查清单
