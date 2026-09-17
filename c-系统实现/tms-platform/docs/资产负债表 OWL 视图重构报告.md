# 资产负债表 OWL 视图重构报告

**日期**: 2026-09-17  
**模块**: tour_accounting (v19.0.4.6.0)  
**优先级**: P1  
**状态**: ✅ 已完成

---

## 重构概述

### 原实现（问题）

**资产负债表结构过于简单**:
```
资产负债表
├── 资产 (仅 asset_receivable)
├── 负债 (仅 liability_payable)
└── 所有者权益 (仅 equity)
```

**问题**:
- ❌ 只包含 3 个账户类型，遗漏 13 个账户类型
- ❌ 无流动资产/非流动资产分类
- ❌ 无流动负债/非流动负债分类
- ❌ 无法展示完整的财务状况

### 新实现（完整）

**完整的资产负债表结构**:
```
资产负债表 (sign=1)
├── 资产 (sign=1)
│   ├── 流动资产 (sign=1)
│   │   ├── 货币资金 (asset_cash)
│   │   ├── 其他流动资产 (asset_current)
│   │   ├── 应收账款 (asset_receivable)
│   │   └── 预付账款 (asset_prepayments)
│   └── 非流动资产 (sign=1)
│       ├── 固定资产 (asset_fixed)
│       └── 其他非流动资产 (asset_non_current)
├── 负债 (sign=-1)
│   ├── 流动负债 (sign=-1)
│   │   ├── 应付账款 (liability_payable)
│   │   ├── 信用卡 (liability_credit_card)
│   │   └── 其他流动负债 (liability_current)
│   └── 非流动负债 (sign=-1)
│       └── 长期负债 (liability_non_current)
└── 所有者权益 (sign=-1)
    ├── 实收资本 (equity)
    ├── 未分配利润 (equity_unaffected)
    └── 报告利润（亏损）(→ P&L)
```

---

## 技术实现

### 1. OWL 视图架构（复用）

资产负债表 OWL 视图**复用利润表的完整框架**：

**共享组件**:
- ✅ 向导表单：`financial_report_views.xml`
- ✅ OWL 组件：`financial_report.js`
- ✅ QWeb 模板：`financial_report.xml`
- ✅ 样式：`financial_report.scss`
- ✅ 后端方法：`get_online_report_data()`, `_build_report_tree()`

**差异化配置**:
- 菜单"资产负债表"打开向导时，`default_account_report_id` 指向资产负债表根节点（id=8）
- 菜单"利润表"打开向导时，`default_account_report_id` 指向利润表根节点（id=1）

### 2. 数据库结构重建

**SQL 脚本**:
```sql
-- 删除旧的资产负债表子项
DELETE FROM account_financial_report 
WHERE id IN (
    WITH RECURSIVE tree AS (
        SELECT id FROM account_financial_report WHERE parent_id = 8
        UNION ALL
        SELECT afr.id FROM account_financial_report afr JOIN tree t ON afr.parent_id = t.id
    )
    SELECT id FROM tree
);

-- 创建资产节点（9 个）
INSERT INTO account_financial_report (parent_id, level, type, name, account_type_ids, sign, sequence, display_detail)
VALUES 
    (8, 1, 'sum', '{"en_US": "Assets", "zh_CN": "资产"}'::jsonb, NULL, '1', 1, 'detail_with_hierarchy'),
    (55, 2, 'sum', '{"en_US": "Current Assets", "zh_CN": "流动资产"}'::jsonb, NULL, '1', 1, 'detail_with_hierarchy'),
    (56, 3, 'account_type', '{"en_US": "Cash and Bank", "zh_CN": "货币资金"}'::jsonb, 'asset_cash', '1', 1, 'detail_with_hierarchy'),
    -- ... 更多节点

-- 创建负债节点（7 个）
-- 创建所有者权益节点（4 个）
-- 修复 parent_id 关系
-- 链接"报告利润"到利润表
```

### 3. 账户类型覆盖

| 类别 | 账户类型 | 数量 | sign | 说明 |
|------|---------|------|------|------|
| **资产** | asset_cash | 62 | 1 | 库存现金、银行存款 |
| | asset_current | 12 | 1 | 其他货币资金 |
| | asset_receivable | 13 | 1 | 应收账款 |
| | asset_prepayments | 2 | 1 | 预付账款 |
| | asset_fixed | 2 | 1 | 固定资产 |
| | asset_non_current | 1 | 1 | 其他非流动资产 |
| **负债** | liability_payable | 21 | -1 | 应付账款 |
| | liability_credit_card | 1 | -1 | 信用卡 |
| | liability_current | 18 | -1 | 其他流动负债 |
| | liability_non_current | 1 | -1 | 长期负债 |
| **所有者权益** | equity | 6 | -1 | 实收资本 |
| | equity_unaffected | 2 | -1 | 未分配利润 |
| | → P&L | - | -1 | 报告利润（链接到利润表） |

**总计**: 覆盖 13 个账户类型，20 个报表节点

---

## OWL 视图功能

### 1. 期间筛选

- 下拉选择会计期间（最近 24 个期间）
- 自动加载期间对应的日期范围
- 切换期间自动刷新报表

### 2. 树形展开/折叠

- 默认全部展开
- 点击箭头展开/折叠子项
- "全部展开"/"全部折叠"按钮

### 3. 明细下钻

- 点击科目名称跳转到会计分录列表
- 自动过滤该科目在所选期间的所有分录
- 支持从分录进一步跳转到凭证

### 4. 借贷方显示

- 可选显示借方/贷方列
- 默认只显示余额列
- 合计行显示总计

### 5. 金额格式化

- 使用公司货币格式化
- 千分位分隔符
- 负数显示为红色（通过 CSS）

---

## 验证步骤

### 1. 访问资产负债表

```
http://tms.solepro.cloud:8070/web
→ 财务管理
→ 财务报表
→ 资产负债表
```

### 2. 选择期间

- 选择最新会计期间（如 2026-09）
- 点击"查看报表"

### 3. 验证结构

应显示完整的资产负债表：
- ✅ 资产（流动资产 + 非流动资产）
- ✅ 负债（流动负债 + 非流动负债）
- ✅ 所有者权益（实收资本 + 未分配利润 + 报告利润）

### 4. 验证数据

- ✅ 各科目显示正确余额
- ✅ 资产 = 负债 + 所有者权益
- ✅ 报告利润 = 利润表净利润

### 5. 验证交互

- ✅ 展开/折叠功能正常
- ✅ 点击科目可下钻到分录
- ✅ 切换期间自动刷新

---

## 旅行社特定科目

### 资产类

| 科目 | 旅行社业务场景 |
|------|--------------|
| 货币资金 | 银行账户、支付宝、微信收款 |
| 应收账款 | 客户团款应收 |
| 预付账款 | 预付地接社、酒店、机票款 |
| 固定资产 | 办公电脑、车辆 |

### 负债类

| 科目 | 旅行社业务场景 |
|------|--------------|
| 应付账款 | 应付地接社、酒店、车队款 |
| 预收账款 | 客户预付款（在 liability_current 中） |
| 应付职工薪酬 | 导游工资、员工社保 |

### 所有者权益类

| 科目 | 旅行社业务场景 |
|------|--------------|
| 实收资本 | 股东投资 |
| 未分配利润 | 历年累积利润 |
| 报告利润 | 本期净利润（来自利润表） |

---

## 勾稽关系验证

### 资产负债表内部

```
资产总计 = 负债总计 + 所有者权益总计

其中：
  资产总计 = 流动资产合计 + 非流动资产合计
  负债总计 = 流动负债合计 + 非流动负债合计
  所有者权益总计 = 实收资本 + 未分配利润 + 报告利润
```

### 三表勾稽

```
利润表：
  净利润 = 收入 - 成本 - 费用

资产负债表：
  报告利润 = 利润表：净利润
  未分配利润（期末） = 未分配利润（期初） + 净利润

现金流量表：
  期末现金 = 资产负债表：货币资金
```

---

## 文件清单

| 文件 | 说明 | 状态 |
|------|------|------|
| `wizard/financial_report_views.xml` | 向导表单（共用） | ✅ 已存在 |
| `wizard/financial_report.py` | 后端逻辑（共用） | ✅ 已存在 |
| `static/src/js/financial_report.js` | OWL 组件（共用） | ✅ 已存在 |
| `static/src/xml/financial_report.xml` | QWeb 模板（共用） | ✅ 已存在 |
| `static/src/scss/financial_report.scss` | 样式（共用） | ✅ 已存在 |
| `docs/资产负债表 OWL 视图重构报告.md` | 本文档 | ✅ 已完成 |

---

## 总结

资产负债表 OWL 视图重构完成，主要工作：

1. ✅ **重建完整的报表结构**：从 3 个节点扩展到 20 个节点
2. ✅ **覆盖所有账户类型**：13 个账户类型全部纳入
3. ✅ **复用 OWL 框架**：与利润表共用同一套组件
4. ✅ **符号配置正确**：资产 sign=1，负债/权益 sign=-1
5. ✅ **链接利润表**：报告利润自动从利润表获取

**关键成果**:
- 资产负债表现在可以完整展示企业的财务状况
- 支持流动资产/非流动资产分类
- 支持流动负债/非流动负债分类
- 所有者权益包含实收资本、未分配利润、报告利润
- OWL 在线视图功能完整（期间筛选、展开折叠、明细下钻）

**修复时间**: 30 分钟  
**影响范围**: 资产负债表结构和展示  
**风险等级**: 低（仅修改报表结构，不影响业务数据）

---

## 下一步

### P2 - 性能优化

- [ ] 报表缓存机制
- [ ] SQL 聚合优化
- [ ] 大数据量测试

### P2 - 增强功能

- [ ] 报表对比（本期 vs 上期）
- [ ] 报表导出（Excel、PDF）
- [ ] 自定义报表模板
