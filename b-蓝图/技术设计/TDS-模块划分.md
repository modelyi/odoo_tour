# TDS-模块划分

> 文档编号：TDS-MOD-001
> 版本：v1.0
> 日期：2026-09-12
> 状态：初稿
> 依据：技术架构思路.md、Odoo功能映射方案.md、易途系统表单字段文档.md

---

## 一、自定义模块清单（14个）

| # | 模块名 | 中文名称 | 核心职责 | 优先级 |
|---|--------|---------|---------|--------|
| 1 | `tour_base` | 旅行社基础模块 | 线路产品、线路分类、发团计划、业务参数 | P0 |
| 2 | `tour_order` | 订单管理模块 | 团队订单、订单报名、并团操作、单团变更 | P0 |
| 3 | `tour_operation` | 计调操作模块 | 资源预订、派导、派车、订房、订餐 | P0 |
| 4 | `tour_resource` | 资源管理模块 | 导游档案、车辆档案、供应商扩展、协议管理 | P0 |
| 5 | `tour_finance` | 财务增强模块 | 收款认领、单团核算、签单单据、对账 | P1 |
| 6 | `tour_shopping` | 购物管理模块 | 购物记录、购物协议、佣金计算 | P1 |
| 7 | `tour_report` | 报表中心模块 | 单团利润、每日收支、导游业绩、客户分析 | P1 |
| 8 | `tour_approval` | 审批流程模块 | 自定义审批流、审批模板、审批权限 | P1 |
| 9 | `tour_b2b` | 同业分销模块 | 同业伙伴、同业订单、同业门户 | P2 |
| 10 | `tour_api` | 小程序API模块 | 微信登录、产品接口、订单接口、支付接口 | P2 |
| 11 | `tour_saas` | SaaS管理模块 | 租户管理、套餐管理、计费管理 | P2 |
| 12 | `tour_ai` | AI增强模块 | AI Agent日志、AI配置、智能推荐 | P3 |
| 13 | `tour_ticket` | 票务管理模块 | 票务计划、预订管理、出票、退票 | P2 |
| 14 | `tour_commission` | 佣金管理模块 | 佣金规则、佣金计算、佣金结算 | P1 |

---

## 二、模块依赖关系图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Odoo 标准模块层                               │
│  ┌──────┐ ┌──────┐ ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐ │
│  │ base │ │ mail │ │ product │ │ account  │ │contacts │ │ fleet │ │
│  └──┬───┘ └──┬───┘ └────┬────┘ └────┬─────┘ └────┬────┘ └───┬───┘ │
└─────┼────────┼──────────┼───────────┼────────────┼──────────┼─────┘
      │        │          │           │            │          │
      └────────┴──────────┴───────────┴────────────┴──────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      旅行社核心模块层                                 │
│                                                                     │
│  ┌──────────────┐                                                   │
│  │  tour_base   │ ◄── 基础模块（线路、分类、发团计划）                │
│  └──────┬───────┘                                                   │
│         │                                                           │
│         ├──────────────────┬──────────────────┬─────────────────┐  │
│         │                  │                  │                 │  │
│         ▼                  ▼                  ▼                 ▼  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────┐ │
│  │  tour_order  │  │tour_resource │  │tour_operation│  │tour_fi-│ │
│  │  (订单)      │  │  (资源)      │  │  (计调)      │  │ nance  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └───┬────┘ │
│         │                  │                  │              │      │
└─────────┼──────────────────┼──────────────────┼──────────────┼──────┘
          │                  │                  │              │
          └──────────────────┴──────────────────┴──────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      旅行社扩展模块层                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────┐ │
│  │tour_shopping │  │  tour_report │  │tour_approval │  │tour_ti-│ │
│  │  (购物)      │  │  (报表)      │  │  (审批)      │  │ cket   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────┘ │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐                                │
│  │tour_commiss- │  │   tour_b2b   │                                │
│  │  ion (佣金)  │  │  (同业分销)  │                                │
│  └──────────────┘  └──────────────┘                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      平台与集成模块层                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   tour_api   │  │   tour_saas  │  │   tour_ai    │             │
│  │ (小程序API)  │  │ (SaaS管理)   │  │  (AI增强)    │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 依赖关系矩阵

| 模块 | 依赖的 Odoo 标准模块 | 依赖的自定义模块 |
|------|---------------------|-----------------|
| `tour_base` | base, mail, product | — |
| `tour_order` | base, mail, product | tour_base |
| `tour_operation` | base, mail | tour_base, tour_order, tour_resource |
| `tour_resource` | base, contacts, fleet | tour_base |
| `tour_finance` | base, account | tour_base, tour_order |
| `tour_shopping` | base | tour_base, tour_order, tour_resource |
| `tour_report` | base, account | tour_base, tour_order, tour_finance |
| `tour_approval` | base, mail | tour_base |
| `tour_b2b` | base, portal | tour_base, tour_order |
| `tour_api` | base | tour_base, tour_order, tour_finance |
| `tour_saas` | base | — (平台端独立) |
| `tour_ai` | base | tour_base, tour_order, tour_resource |
| `tour_ticket` | base | tour_base, tour_order, tour_operation |
| `tour_commission` | base, account | tour_base, tour_order, tour_shopping |

---

## 三、各模块详细设计

### 3.1 tour_base — 旅行社基础模块

**职责**：
- 线路产品管理（tour.line）
- 线路分类管理（tour.line.type）
- 发团计划管理（tour.departure）
- 业务参数配置（结算方式、业务类型、基础数据）

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.line` | `_inherit='product.template'` | 线路产品（82字段映射） |
| `tour.line.type` | `_inherit='product.category'` | 线路分类（25字段，树形） |
| `tour.departure` | 新建 | 发团计划（日期/余位/价格） |
| `tour.line.detail` | 新建 | 行程明细（第N天行程） |
| `tour.pay.way` | 新建 | 结算方式（7条基础数据） |
| `tour.biz.type` | 新建 | 业务类型（5条基础数据） |
| `tour.base.item` | 新建 | 通用基础数据（类型2/3/5/职务） |

**依赖**：
- Odoo 标准：`base`, `mail`, `product`
- 自定义：无

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 模型定义 + 字段映射 | 5 |
| 视图设计（列表/表单/搜索） | 4 |
| 数据迁移脚本 | 3 |
| 单元测试 | 2 |
| **合计** | **14 人天** |

---

### 3.2 tour_order — 订单管理模块

**职责**：
- 团队订单管理（tour.plan，137字段）
- 订单报名管理（tour.plan.reg，77字段）
- 并团操作（tour.merge）
- 单团变更（tour.plan.change）

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.plan` | 新建 | 团队订单（86,925条，12种业务模式） |
| `tour.plan.reg` | 新建 | 订单报名（86,753条，含并团逻辑） |
| `tour.merge` | 新建 | 并团操作记录 |
| `tour.plan.change` | 新建 | 单团变更记录 |

**业务模式支持**：
- DT (1,2) — 团队输单
- DSK (12) — 团期计划
- DSS (13) — 散客单组
- DSN (14,15) — 散客并团
- DTO (21) — 组团团队
- DSO (31) — 组团散客
- DD (41) — 代订项目
- 自由行 (51,52)
- 等 12 种

**依赖**：
- Odoo 标准：`base`, `mail`, `product`
- 自定义：`tour_base`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 模型定义 + 字段映射 | 8 |
| 并团逻辑实现 | 6 |
| 视图设计 + 向导 | 6 |
| 状态机 + 工作流 | 4 |
| 数据迁移脚本 | 5 |
| 单元测试 | 4 |
| **合计** | **33 人天** |

---

### 3.3 tour_operation — 计调操作模块

**职责**：
- 资源预订管理（酒店、餐厅、车辆、导游）
- 派导管理（导游分配）
- 派车管理（车辆调度）
- 订房管理（酒店预订）
- 订餐管理（餐厅预订）
- 计调工作台（Dashboard）

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.booking` | 新建 | 资源预订（通用） |
| `tour.guide.assign` | 新建 | 派导记录 |
| `tour.vehicle.assign` | 新建 | 派车记录 |
| `tour.hotel.booking` | 新建 | 酒店预订 |
| `tour.meal.booking` | 新建 | 餐厅预订 |

**依赖**：
- Odoo 标准：`base`, `mail`
- 自定义：`tour_base`, `tour_order`, `tour_resource`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 模型定义 | 5 |
| 派导/派车逻辑 | 6 |
| 计调工作台 UI | 5 |
| 资源冲突检测 | 3 |
| 单元测试 | 3 |
| **合计** | **22 人天** |

---

### 3.4 tour_resource — 资源管理模块

**职责**：
- 导游档案管理（tour.guide，64字段，2,173条）
- 车辆档案管理（fleet.vehicle 扩展，49字段，71条）
- 供应商扩展（res.partner 扩展，117字段，10种类型）
- 协议管理（供应商合作协议）

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.guide` | 新建 | 导游档案（64字段） |
| `fleet.vehicle` | `_inherit` | 车辆档案扩展（49字段） |
| `res.partner` | `_inherit` | 供应商扩展（117字段） |
| `tour.agreement` | 新建 | 供应商协议 |

**供应商类型映射**：
- 客户 (SupTypeID=1)
- 地接社 (SupTypeID=2)
- 酒店 (SupTypeID=4)
- 餐厅 (SupTypeID=5)
- 车辆公司 (SupTypeID=6)
- 票务公司 (SupTypeID=7)
- 景区景点 (SupTypeID=8)
- 购物店 (SupTypeID=9)
- 保险公司 (SupTypeID=10)
- 自费公司 (SupTypeID=13)

**依赖**：
- Odoo 标准：`base`, `contacts`, `fleet`
- 自定义：`tour_base`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| res.partner 扩展（117字段） | 6 |
| tour.guide 模型 | 4 |
| fleet.vehicle 扩展 | 3 |
| 协议管理 | 3 |
| 数据迁移脚本 | 4 |
| 单元测试 | 3 |
| **合计** | **23 人天** |

---

### 3.5 tour_finance — 财务增强模块

**职责**：
- 收款认领管理（tour.payment.claim，30字段）
- 单团核算（tour.plan.account）
- 签单单据管理（tour.sign.bill）
- 往来对账（tour.reconciliation）
- 批量收付款向导

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.payment.claim` | 新建 | 收款登记（30字段） |
| `tour.plan.account` | 新建 | 单团核算 |
| `tour.sign.bill` | 新建 | 签单单据 |
| `tour.reconciliation` | 新建 | 对账记录 |

**依赖**：
- Odoo 标准：`base`, `account`
- 自定义：`tour_base`, `tour_order`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 收款认领模型 | 4 |
| 单团核算逻辑 | 6 |
| 签单单据 | 3 |
| 对账功能 | 5 |
| 批量操作向导 | 3 |
| 单元测试 | 4 |
| **合计** | **25 人天** |

---

### 3.6 tour_shopping — 购物管理模块

**职责**：
- 购物记录管理（团队购物明细）
- 购物协议管理（购物店合作协议）
- 佣金计算（导游/旅行社分成）
- 购物分析报表

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.shop.record` | 新建 | 购物记录 |
| `tour.shop.agreement` | 新建 | 购物协议 |
| `tour.commission` | 新建 | 佣金记录 |

**依赖**：
- Odoo 标准：`base`
- 自定义：`tour_base`, `tour_order`, `tour_resource`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 购物记录模型 | 3 |
| 购物协议 | 3 |
| 佣金计算逻辑 | 5 |
| 购物分析报表 | 3 |
| 单元测试 | 2 |
| **合计** | **16 人天** |

---

### 3.7 tour_report — 报表中心模块

**职责**：
- 单团利润报表
- 每日收支报表
- 导游业绩报表
- 客户分析报表
- 管理看板（Dashboard）

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.report.plan.profit` | 新建（Transient） | 单团利润报表 |
| `tour.report.daily.revenue` | 新建（Transient） | 每日收支报表 |
| `tour.report.guide.performance` | 新建（Transient） | 导游业绩报表 |
| `tour.report.customer.analysis` | 新建（Transient） | 客户分析报表 |

**依赖**：
- Odoo 标准：`base`, `account`
- 自定义：`tour_base`, `tour_order`, `tour_finance`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 单团利润报表 | 4 |
| 每日收支报表 | 3 |
| 导游业绩报表 | 3 |
| 客户分析报表 | 3 |
| 管理看板 UI | 4 |
| 单元测试 | 2 |
| **合计** | **19 人天** |

---

### 3.8 tour_approval — 审批流程模块

**职责**：
- 自定义审批流程配置
- 审批模板管理
- 审批权限控制
- 审批历史记录

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.approval.flow` | 新建 | 审批流程定义 |
| `tour.approval.template` | 新建 | 审批模板 |
| `tour.approval.record` | 新建 | 审批记录 |

**审批场景**：
- 收款审批
- 付款审批
- 导游借款审批
- 订单变更审批
- 大额退款审批

**依赖**：
- Odoo 标准：`base`, `mail`
- 自定义：`tour_base`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 审批流程引擎 | 6 |
| 审批模板 | 3 |
| 审批权限 | 3 |
| 审批历史 | 2 |
| 单元测试 | 3 |
| **合计** | **17 人天** |

---

### 3.9 tour_b2b — 同业分销模块

**职责**：
- 同业伙伴管理
- 同业订单管理
- 同业门户（Portal）
- 同业结算

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.b2b.partner` | 新建 | 同业伙伴 |
| `tour.b2b.order` | 新建 | 同业订单 |
| `tour.b2b.settlement` | 新建 | 同业结算 |

**依赖**：
- Odoo 标准：`base`, `portal`
- 自定义：`tour_base`, `tour_order`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 同业伙伴模型 | 3 |
| 同业订单 | 5 |
| 同业门户 UI | 6 |
| 同业结算 | 4 |
| 单元测试 | 3 |
| **合计** | **21 人天** |

---

### 3.10 tour_api — 小程序API模块

**职责**：
- 微信登录认证
- 产品接口（线路/发团计划）
- 订单接口（创建/查询/取消）
- 支付接口（微信支付）
- 导游接口（报账）
- Token 管理

**核心组件**：
| 组件 | 类型 | 说明 |
|------|------|------|
| `controllers/auth.py` | Controller | 微信登录 |
| `controllers/product.py` | Controller | 产品接口 |
| `controllers/order.py` | Controller | 订单接口 |
| `controllers/payment.py` | Controller | 支付接口 |
| `controllers/guide.py` | Controller | 导游接口 |
| `security/api_token.py` | Model | Token 管理 |

**API 路由**：
```
/api/v1/auth/wx-login      # 微信登录
/api/v1/product/lines       # 线路列表
/api/v1/product/departures  # 发团计划
/api/v1/order/create        # 创建订单
/api/v1/order/list          # 订单列表
/api/v1/payment/wx-pay      # 微信支付
/api/v1/guide/trips         # 导游带团列表
/api/v1/guide/expense       # 费用录入
```

**依赖**：
- Odoo 标准：`base`
- 自定义：`tour_base`, `tour_order`, `tour_finance`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 微信登录 + Token | 4 |
| 产品接口 | 3 |
| 订单接口 | 5 |
| 支付接口 | 5 |
| 导游接口 | 3 |
| API 文档 | 2 |
| 单元测试 | 4 |
| **合计** | **26 人天** |

---

### 3.11 tour_saas — SaaS管理模块

**职责**：
- 租户管理（创建/停用/删除）
- 套餐管理（基础版/专业版/企业版）
- 计费管理（按租户/按月）
- 租户初始化脚本

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `saas.tenant` | 新建 | 租户管理 |
| `saas.plan` | 新建 | 套餐管理 |
| `saas.billing` | 新建 | 计费管理 |

**租户生命周期**：
1. 注册/付费 → 触发 API
2. 自动创建 PostgreSQL 数据库（从模板库 clone）
3. 安装旅行社核心模块集
4. 初始化基础数据
5. 配置域名 + SSL
6. 发送管理员账号邮件

**依赖**：
- Odoo 标准：`base`
- 自定义：无（平台端独立）

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 租户管理模型 | 4 |
| 套餐管理 | 3 |
| 计费管理 | 4 |
| 租户初始化脚本 | 5 |
| 域名/SSL 自动化 | 4 |
| 单元测试 | 3 |
| **合计** | **23 人天** |

---

### 3.12 tour_ai — AI增强模块

**职责**：
- AI Agent 日志记录
- AI 配置管理
- 智能推荐（线路/并团方案）
- 智能匹配（收款认领/派导）

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.agent.log` | 新建 | AI Agent 日志 |
| `tour.ai.config` | 新建 | AI 配置 |

**AI 能力分层**：
- **Layer 1**：规则引擎（Odoo 原生）
- **Layer 2**：AI 助手（Odoo 19 内置）
- **Layer 3**：Agentic AI（Odoo 20，自主执行）

**AI 应用场景**：
- 线路描述自动生成
- 并团方案智能推荐
- 收款智能匹配
- 派导智能推荐
- 财务预测

**依赖**：
- Odoo 标准：`base`
- 自定义：`tour_base`, `tour_order`, `tour_resource`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| AI Agent 日志模型 | 3 |
| AI 配置管理 | 2 |
| 智能推荐接口 | 5 |
| 智能匹配接口 | 5 |
| Odoo 19 AI 集成 | 4 |
| 单元测试 | 3 |
| **合计** | **22 人天** |

---

### 3.13 tour_ticket — 票务管理模块

**职责**：
- 票务计划管理
- 预订管理
- 出票管理
- 退票管理

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.traffic.ticket` | 新建 | 票务档案 |
| `tour.ticket.booking` | 新建 | 票务预订 |
| `tour.ticket.issue` | 新建 | 出票记录 |
| `tour.ticket.refund` | 新建 | 退票记录 |

**依赖**：
- Odoo 标准：`base`
- 自定义：`tour_base`, `tour_order`, `tour_operation`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 票务模型 | 4 |
| 预订管理 | 4 |
| 出票/退票 | 4 |
| 单元测试 | 2 |
| **合计** | **14 人天** |

---

### 3.14 tour_commission — 佣金管理模块

**职责**：
- 佣金规则配置
- 佣金自动计算
- 佣金结算
- 佣金报表

**核心模型**：
| 模型 | 类型 | 说明 |
|------|------|------|
| `tour.commission.rule` | 新建 | 佣金规则 |
| `tour.commission.calc` | 新建 | 佣金计算记录 |
| `tour.commission.settlement` | 新建 | 佣金结算 |

**依赖**：
- Odoo 标准：`base`, `account`
- 自定义：`tour_base`, `tour_order`, `tour_shopping`

**预估工作量**：
| 任务 | 人天 |
|------|------|
| 佣金规则模型 | 4 |
| 佣金计算引擎 | 5 |
| 佣金结算 | 3 |
| 佣金报表 | 3 |
| 单元测试 | 2 |
| **合计** | **17 人天** |

---

## 四、与 Odoo 标准模块的关系

### 4.1 标准模块依赖清单

| Odoo 标准模块 | 用途 | 依赖的自定义模块 |
|--------------|------|-----------------|
| `base` | 核心框架（用户/公司/权限） | 所有模块 |
| `mail` | 消息/跟踪/订阅 | tour_base, tour_order, tour_operation, tour_approval |
| `product` | 产品管理（product.template/category） | tour_base, tour_order |
| `account` | 会计/发票/付款 | tour_finance, tour_report, tour_commission |
| `contacts` | 联系人管理（res.partner） | tour_resource |
| `fleet` | 车队管理（fleet.vehicle） | tour_resource |
| `portal` | 门户功能（外部用户访问） | tour_b2b |

### 4.2 扩展关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Odoo 标准模块                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  product.template ──────── tour.line (扩展)                     │
│  product.category ──────── tour.line.type (扩展)                │
│  res.partner ───────────── tour_resource (扩展 117 字段)        │
│  fleet.vehicle ─────────── tour_resource (扩展 49 字段)         │
│  account.payment ───────── tour.payment.claim (独立但关联)      │
│  res.partner.bank ──────── tour_resource (扩展)                 │
│  hr.department ─────────── tour_base (扩展)                     │
│  res.users ─────────────── tour_base (扩展)                     │
│  res.company ───────────── tour_base (扩展)                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、模块加载顺序建议

### 5.1 开发阶段加载顺序

**Phase 1（核心业务闭环）**：
```
1. tour_base          # 基础模块（线路、分类、发团计划）
2. tour_resource      # 资源管理（导游、车辆、供应商）
3. tour_order         # 订单管理（团队订单、报名、并团）
4. tour_operation     # 计调操作（派导、派车、预订）
5. tour_finance       # 财务增强（收款、核算、对账）
```

**Phase 2（财务深化）**：
```
6. tour_shopping      # 购物管理
7. tour_commission    # 佣金管理
8. tour_approval      # 审批流程
9. tour_report        # 报表中心
```

**Phase 3（扩展功能）**：
```
10. tour_ticket       # 票务管理
11. tour_b2b          # 同业分销
12. tour_api          # 小程序API
```

**Phase 4（平台与AI）**：
```
13. tour_saas         # SaaS管理
14. tour_ai           # AI增强
```

### 5.2 生产环境加载顺序

```python
# odoo.conf 中的 addons_path 和 server_wide_modules
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons

# 模块安装顺序（依赖自动解析）
# 1. Odoo 标准模块：base, mail, product, account, contacts, fleet, portal
# 2. tour_base
# 3. tour_resource
# 4. tour_order
# 5. tour_operation
# 6. tour_finance
# 7. tour_shopping
# 8. tour_commission
# 9. tour_approval
# 10. tour_report
# 11. tour_ticket
# 12. tour_b2b
# 13. tour_api
# 14. tour_saas
# 15. tour_ai
```

---

## 六、工作量汇总

### 6.1 按模块汇总

| 模块 | 人天 | 优先级 | 阶段 |
|------|------|--------|------|
| tour_base | 14 | P0 | Phase 1 |
| tour_order | 33 | P0 | Phase 1 |
| tour_operation | 22 | P0 | Phase 1 |
| tour_resource | 23 | P0 | Phase 1 |
| tour_finance | 25 | P1 | Phase 1 |
| tour_shopping | 16 | P1 | Phase 2 |
| tour_commission | 17 | P1 | Phase 2 |
| tour_approval | 17 | P1 | Phase 2 |
| tour_report | 19 | P1 | Phase 2 |
| tour_ticket | 14 | P2 | Phase 3 |
| tour_b2b | 21 | P2 | Phase 3 |
| tour_api | 26 | P2 | Phase 3 |
| tour_saas | 23 | P2 | Phase 4 |
| tour_ai | 22 | P3 | Phase 4 |
| **合计** | **292 人天** | | |

### 6.2 按阶段汇总

| 阶段 | 模块数 | 人天 | 预计周期（2人团队） |
|------|--------|------|-------------------|
| Phase 1（核心闭环） | 5 | 117 | 3 个月 |
| Phase 2（财务深化） | 4 | 69 | 2 个月 |
| Phase 3（扩展功能） | 3 | 61 | 1.5 个月 |
| Phase 4（平台与AI） | 2 | 45 | 1 个月 |
| **总计** | **14** | **292** | **7.5 个月** |

### 6.3 里程碑规划

| 里程碑 | 时间 | 交付物 |
|--------|------|--------|
| M1 - 核心业务上线 | 2026 Q1 | Phase 1 模块 + 数据迁移 + 用户培训 |
| M2 - 财务深化完成 | 2026 Q2 | Phase 2 模块 + 报表 + 审批流程 |
| M3 - 小程序上线 | 2026 Q3 | Phase 3 模块 + 微信小程序 + 同业门户 |
| M4 - SaaS 平台上线 | 2026 Q4 | Phase 4 模块 + 多租户 + AI 功能 |

---

## 附录 A：模块目录结构示例

```
tms-addons/
├── tour_base/
│   ├── __manifest__.py
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tour_line.py
│   │   ├── tour_line_type.py
│   │   ├── tour_departure.py
│   │   └── tour_config.py
│   ├── views/
│   │   ├── tour_line_views.xml
│   │   ├── tour_line_type_views.xml
│   │   └── tour_departure_views.xml
│   ├── data/
│   │   └── tour_data.xml
│   ├── security/
│   │   ├── ir.model.access.csv
│   │   └── tour_security.xml
│   └── static/
│       └── description/
│           └── icon.png
│
├── tour_order/
│   ├── __manifest__.py
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tour_plan.py
│   │   ├── tour_plan_reg.py
│   │   ├── tour_merge.py
│   │   └── tour_plan_change.py
│   ├── wizard/
│   │   ├── __init__.py
│   │   └── merge_wizard.py
│   ├── views/
│   │   ├── tour_plan_views.xml
│   │   ├── tour_plan_reg_views.xml
│   │   └── merge_wizard_views.xml
│   └── security/
│       └── ir.model.access.csv
│
└── ... (其他模块类似结构)
```

---

## 附录 B：__manifest__.py 示例

```python
# tour_base/__manifest__.py
{
    'name': '旅行社基础模块',
    'version': '19.0.1.0.0',
    'category': 'Travel/Tour',
    'summary': '线路产品、线路分类、发团计划、业务参数',
    'description': """
        旅行社管理系统基础模块
        - 线路产品管理（tour.line）
        - 线路分类管理（tour.line.type）
        - 发团计划管理（tour.departure）
        - 业务参数配置
    """,
    'author': 'Hailuo Travel',
    'website': 'https://example.com',
    'depends': ['base', 'mail', 'product'],
    'data': [
        'security/tour_security.xml',
        'security/ir.model.access.csv',
        'data/tour_data.xml',
        'views/tour_line_views.xml',
        'views/tour_line_type_views.xml',
        'views/tour_departure_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/tour_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
```
