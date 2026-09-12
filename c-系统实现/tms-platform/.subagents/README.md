# Subagent 角色配置

## 概述

本项目采用多 subagent 协作开发模式，将开发任务拆分为不同角色，各司其职：

- **product_manager**: 产品经理（产品规划、需求优先级、利益相关者协调）
- **product_architect**: 产品架构师（技术架构、模块设计、系统集成）
- **tour_ba**: 旅行业务分析师（旅行业务需求、用户故事、功能规格）
- **finance_ba**: 财务业务分析师（财务需求、会计规则、对账流程）
- **dev_odoo**: Odoo 开发工程师（业务逻辑、视图、控制器）
- **devops**: 运维工程师（系统部署、运维、监控、配置）
- **dev_qa**: 开发质量保证（代码审查、自动化测试）
- **uat_qa**: 用户验收测试（端到端验证、用户体验）

## 目录结构

```
.subagents/
├── README.md                  # 本文件
├── manifest.json              # 角色配置清单
├── product_manager.md         # 产品经理角色定义
├── product_architect.md       # 产品架构师角色定义
├── tour_ba.md                 # 旅行业务分析师角色定义
├── finance_ba.md              # 财务业务分析师角色定义
├── dev_odoo.md                # Odoo 开发工程师角色定义
├── devops.md                  # 运维工程师角色定义
├── dev_qa.md                  # 开发质量保证角色定义
└── uat_qa.md                  # 用户验收测试角色定义
```

## 角色职责

| 角色 | 职责 | 关注点 |
|------|------|--------|
| product_manager | 产品规划、需求优先级、利益相关者协调 | 产品路线图、里程碑、ROI |
| product_architect | 技术架构、模块设计、系统集成 | 架构可扩展性、性能、技术债务 |
| tour_ba | 旅行业务需求分析 | 业务流程、用户故事、功能规格 |
| finance_ba | 财务业务需求分析 | 会计规则、对账流程、佣金计算 |
| dev_odoo | 编写代码、实现功能 | 业务逻辑、代码质量 |
| devops | 部署运维、环境配置 | 系统稳定性、性能 |
| dev_qa | 代码审查、测试验证 | 代码规范、测试覆盖 |
| uat_qa | 用户验收、体验验证 | 业务流程、用户体验 |

## 使用方式

### 1. 查看角色定义

```bash
cat .subagents/product_manager.md
cat .subagents/product_architect.md
cat .subagents/tour_ba.md
cat .subagents/finance_ba.md
cat .subagents/dev_odoo.md
cat .subagents/devops.md
cat .subagents/dev_qa.md
cat .subagents/uat_qa.md
```

### 2. 委派任务时引用

在委派任务时，可以指定使用特定角色：

```
根据 .subagents/dev_odoo.md 的角色定义，开发 tour_order 模块...
```

### 3. 更新角色配置

如需调整角色职责，直接编辑对应的 `.md` 文件，并更新 `manifest.json`。

## 工作流程

```
用户需求
    ↓
[product_manager] 产品规划（路线图、优先级）
    ↓
[product_architect] 技术架构（模块设计、数据模型）
    ↓
[tour_ba + finance_ba] 业务分析（并行）
    ↓
[dev_odoo] 开发实现
    ↓
[dev_qa] 代码审查 + 测试
    ↓
[devops] 部署到环境
    ↓
[uat_qa] 用户验收测试
    ↓
✓ 上线
```

## 协作规范

1. **product_manager** 制定产品路线图和需求优先级，协调 **tour_ba** 和 **finance_ba** 的工作分配
2. **product_architect** 根据产品路线图设计技术架构，指导 **dev_odoo** 的技术实现方向
3. **tour_ba + finance_ba** 并行进行业务分析，输出需求文档和功能规格
4. **dev_odoo** 根据架构设计和 BA 输出的规格进行开发，完成后提交代码并通知 **dev_qa** 审查
5. **dev_qa** 审查通过后，通知 **devops** 部署
6. **devops** 部署完成后，通知 **uat_qa** 进行验收测试
7. **uat_qa** 发现问题，反馈给 **product_manager**、**tour_ba/finance_ba** 和 **dev_odoo** 修复

## 扩展角色

如需添加新角色：

1. 在 `.subagents/` 目录创建 `role_name.md`
2. 在 `manifest.json` 中添加角色条目
3. 在本 README 中更新角色列表和工作流程

## 产品管理分工说明

**product_manager（产品经理）** 负责：
- 产品愿景和战略规划
- 产品路线图制定（Phase 1-4）
- 需求优先级排序（P0/P1/P2/P3）
- 利益相关者沟通（用户、管理层、开发团队）
- 迭代计划和里程碑管理
- 协调 tour_ba 和 finance_ba 的工作分配
- 产品指标跟踪（功能覆盖率、用户满意度、Bug 率）

**product_architect（产品架构师）** 负责：
- 系统架构设计（Odoo 19 技术栈）
- 模块划分和依赖关系设计（14 个自定义模块）
- 数据模型设计（PostgreSQL + Odoo ORM）
- API 接口设计（小程序、同业分销、第三方集成）
- 集成架构设计（Nginx、Redis、Docker）
- 性能优化和扩展性设计
- 技术债务管理
- 指导 dev_odoo 的技术实现

## 业务分析分工说明

**tour_ba（旅行业务分析师）** 负责：
- 线路产品设计、发团计划
- 收客订单、并团逻辑
- 计调操作（派车派导、订房订餐）
- 导游管理、购物佣金
- 同业分销、自由行、代订服务

**finance_ba（财务业务分析师）** 负责：
- 收付款流程、收款认领
- 10类对账（团款/地接/车费/门票/房费等）
- 佣金分成计算规则
- 审批流程设计
- 财务报表、单团核算

两个 BA 角色在涉及交叉业务时需要协调：
- 订单金额、报价 → tour_ba 定义，finance_ba 审核
- 收付款 → finance_ba 定义，tour_ba 确认业务流程
- 佣金计算 → finance_ba 定义规则，tour_ba 确认业务逻辑

## 决策权限矩阵

| 决策类型 | product_manager | product_architect | tour_ba/finance_ba | dev_odoo |
|---------|-----------------|-------------------|-------------------|----------|
| 需求优先级 | ✅ 决定 | 协商 | 建议 | 建议 |
| 技术选型 | 协商 | ✅ 决定 | 建议 | 建议 |
| 模块划分 | 协商 | ✅ 决定 | 输入 | 建议 |
| 业务规则 | 审批 | 协商 | ✅ 决定 | 实现 |
| 代码规范 | - | ✅ 决定 | - | 遵循 |
| 发布时间 | ✅ 决定 | 协商 | - | - |
