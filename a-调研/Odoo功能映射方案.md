# 易途 → Odoo 功能映射方案

> 目标：在 Odoo 中实现易途旅行社管理系统的核心功能
> 数据来源：http://et.example.com/ API 实际抓取（2026-09-12）

## Odoo 版本建议

推荐使用 **Odoo 17/18 社区版 + 自定义模块**，利用 Odoo 现有模块减少开发量。

---

## 模块映射总览

| 易途功能模块 | Odoo 对应模块 | 开发方式 |
|-------------|--------------|---------|
| 线路产品管理 | 产品（product.template） | 扩展 + 新建发团计划模型 |
| 订单管理 | 销售订单（sale.order） | 扩展 + 新建并团/变更模型 |
| 计调操作 | 自定义模块 tour.operation | 新建 |
| 地接/组团业务 | sale.order + 自定义 | 扩展 + 新建 |
| 客户管理 CRM | CRM + res.partner | 扩展 |
| 供应商/资源管理 | res.partner（supplier） | 扩展 + 分类 |
| 财务管理 | 会计（account） | 扩展 + 新建 |
| 收付款审批 | 审批流 | 配置 + 扩展 |
| 发票管理 | account.move | 扩展 |
| 票务管理 | 自定义模块 tour.ticket | 新建 |
| 购物佣金计算 | 自定义模块 tour.commission | 新建 |
| 签单单据管理 | 自定义模块 tour.signbill | 新建 |
| 报表与决策分析 | 报表 + BI | 扩展 + 自定义 |
| 系统管理/权限 | Odoo 权限体系 | 配置 |
| 同业分销 | 门户 + 自定义 | 新建 |
| 导游报账 | 自定义模块（移动端） | 新建 |
| 车队管理 | Fleet 模块 | 扩展 fleet |
| 短信通知 | Odoo SMS / 短信网关 | 配置 |
| 小程序商城 | Odoo 电商 + 前端 | 扩展 website_sale |
| 办公管理 | 自定义模块 tour.oa | 新建 |
| 支付宝费控 | 自定义模块 tour.alipay | 新建 |

---

## 数据模型详细映射（基于实际 API 字段）

### 1. 线路产品 → product.template + tour.line

**易途实际字段**（70+ 字段，API: `/Line/GetSearchList/ResMng.LineList`）：

| 易途字段 | 含义 | Odoo 映射 |
|---------|------|----------|
| LineID | 线路ID | tour.line.id |
| LineTypeID | 线路分类ID | product.category |
| LineType | 分类名称（品质纯玩/深度） | product.category.name |
| LineCode | 线路编号 | tour.line.code |
| HelpCode | 助记码 | tour.line.help_code |
| LineName | 线路名称 | product.template.name |
| DayNum | 天数 | tour.line.day_num |
| ValidDayNum | 有效天数 | tour.line.valid_day_num |
| SendPlace | 出发地 | tour.line.send_place |
| EndPlace | 目的地 | tour.line.end_place |
| SendTraffic | 出发交通 | tour.line.send_traffic |
| EndTraffic | 返回交通 | tour.line.end_traffic |
| SrvText | 服务说明 | tour.line.srv_text (HTML) |
| Remark | 备注 | tour.line.remark |
| ShoppingInfo | 购物信息 | tour.line.shopping_info |
| SelfPaidItem | 自费项目 | tour.line.self_paid_item |
| WarmHint | 温馨提示 | tour.line.warm_hint |
| AdultPrice | 成人价 | tour.line.adult_price |
| ChildPrice | 儿童价 | tour.line.child_price |
| OldManPrice | 老人价 | tour.line.old_man_price |
| BabyPrice | 婴儿价 | tour.line.baby_price |
| StudentPrice | 学生价 | tour.line.student_price |
| FeeInclude | 费用包含 | tour.line.fee_include |
| FeeExclude | 费用不含 | tour.line.fee_exclude |
| LineDetailsRich | 行程详情(富文本) | tour.line.details_rich (HTML) |
| LineFeatureRich | 线路特色(富文本) | tour.line.feature_rich (HTML) |
| Attentions | 注意事项 | tour.line.attentions |
| LineScore | 线路评分 | tour.line.score |
| SpecialRecommendation | 特别推荐 | tour.line.special_recommendation |
| UseChk | 启用状态 | product.template.active |
| OpUserID/Name | 操作人 | write_uid |
| OpDptID/Name | 操作部门 | tour.line.department_id |
| OpCmpID/Name | 操作公司 | company_id |
| DJSupplierID/Name | 地接社 | tour.line.dj_supplier_id |
| Guide_ShareRate | 导游分成比例 | tour.line.guide_share_rate |
| Guide_Premium | 导游奖金 | tour.line.guide_premium |
| FromProvince/City | 出发省市 | tour.line.from_province/city |
| ToProvince/City | 目的省市 | tour.line.to_province/city |
| IsSpecial | 是否特殊线路 | tour.line.is_special |
| IsJw | 是否境外 | tour.line.is_jw |
| IsDJS | 是否地接社 | tour.line.is_djs |
| AuditChk | 审核状态 | tour.line.audit_chk |
| LineAttachmentList | 附件列表 | product.template.attachment |
| LineMarks | 线路标签 | tour.line.marks |
| LineStrategy | 线路攻略 | tour.line.strategy |

**新建模型**：
- `tour.line`：线路主表（扩展 product.template 或独立模型）
- `tour.line.detail`：线路行程明细（第1天、第2天...）
- `tour.departure.plan`：发团计划（日期、余位、价格、状态）
- `tour.line.type`：线路分类

### 2. 订单/团单 → sale.order + tour.plan

**业务模式**（12种）：

| 代号 | 模式 | Odoo 映射 |
|------|------|----------|
| DT (1,2) | 团队输单 | tour.plan (type='dt') |
| DSK (12) | 团期计划 | tour.plan (type='dsk') |
| DSS (13) | 散客单组 | tour.plan (type='dss') |
| DSN (14,15) | 散客并团 | tour.plan (type='dsn') + tour.merge |
| 流转 (16) | 内部流转 | tour.plan (type='lz') |
| 产品计划 (17) | 发布线路协议 | tour.plan (type='pp') |
| 关键字并团 (18) | 关键字并团 | tour.plan (type='key') |
| DTO (21) | 组团团队 | tour.plan (type='dto') |
| DSO (31) | 组团散客 | tour.plan (type='dso') |
| DD (41) | 代订项目 | tour.plan (type='dd') |
| 自由行 (51,52) | 自由行 | tour.plan (type='freedom') |
| 共享协议 (71) | 共享协议 | tour.plan (type='share') |

**订单类型**：DT(团队)、DS(散客)、ZT(组团团队)、ZS(组团散客)、DD(代订)、JS(接送)、BG(变更)

**订单来源**：NB(内部)、MS(门市)、TH(同行)、LZ(集团流转)

**代订项目类型**：门(1)、房(2)、签(3)、票(4)、餐(5)、车(6)、险(7)、收(8)、支(9)、导(10)、其他(99)

### 3. 供应商/资源 → res.partner

**供应商分类**（supTypeId）：

| ID | 类型 | Odoo 映射 |
|----|------|----------|
| 1 | 客户档案 | res.partner (customer) |
| 2 | 地接社档案 | res.partner (supplier, category='地接社') |
| 4 | 酒店档案 | res.partner (supplier, category='酒店') |
| 5 | 餐厅档案 | res.partner (supplier, category='餐厅') |
| 6 | 车辆公司 | res.partner (supplier, category='车辆公司') |
| 7 | 票务公司 | res.partner (supplier, category='票务公司') |
| 8 | 景区景点 | res.partner (supplier, category='景区') |
| 9 | 购物店档案 | res.partner (supplier, category='购物店') |
| 10 | 保险公司 | res.partner (supplier, category='保险公司') |
| 11 | 签证公司 | res.partner (supplier, category='签证公司') |
| 13 | 自费公司 | res.partner (supplier, category='自费公司') |
| 15 | 平台商档案 | res.partner (supplier, category='平台商') |

**导游档案**：独立模型 `tour.guide`

**车辆档案**：扩展 `fleet.vehicle`

**票务列表**：独立模型 `tour.traffic.ticket`

---

```
旅行社管理
├── 仪表盘
├── 产品管理
│   ├── 线路产品
│   └── 发团计划
├── 业务管理
│   ├── 订单管理
│   │   ├── 组团订单
│   │   ├── 地接订单
│   │   ├── 小包团/自由行
│   │   ├── 接送业务
│   │   └── 订单回收站
│   ├── 计调操作
│   │   ├── 资源预订
│   │   ├── 派车管理
│   │   ├── 派导管理
│   │   └── 进店管理
│   └── 票务管理
│       ├── 票务计划
│       ├── 预订管理
│       ├── 出票管理
│       └── 退票管理
├── 客户管理
│   ├── 客户列表
│   ├── 客户跟进
│   └── 合同管理
├── 供应商管理
│   ├── 供应商列表
│   ├── 签单单据
│   └── 采购中心
├── 财务管理
│   ├── 收款管理
│   │   ├── 收款登记
│   │   └── 收款认领
│   ├── 付款管理
│   ├── 审批中心
│   │   ├── 收款审批
│   │   ├── 付款审批
│   │   └── 导游借款审批
│   ├── 单团核算
│   ├── 往来对账
│   ├── 佣金计算
│   ├── 发票管理
│   │   ├── 开票管理
│   │   └── 收票管理
│   └── 期初余额
├── 报表中心
│   ├── 销售统计
│   ├── 财务报表
│   ├── 利润分析
│   └── 客户分析
├── 车队管理
│   ├── 车辆管理
│   ├── 派车调度
│   ├── 结算管理
│   └── 绩效考核
├── 系统设置
│   ├── 用户与权限
│   ├── 审批流程配置
│   ├── 业务参数
│   └── 操作日志
└── 同业分销（门户）
    ├── 产品发布
    ├── 在线预订
    └── 同业结算
```

---

## 开发优先级建议

### 第一期（核心业务闭环）
1. 线路产品管理
2. 订单管理（含并团）
3. 计调操作（资源预订、派车、派导）
4. 基础财务管理（收付款、单团核算）
5. 客户管理

### 第二期（财务深化）
6. 往来对账
7. 佣金计算
8. 发票管理
9. 审批流程
10. 报表

### 第三期（扩展功能）
11. 票务管理
12. 签单单据
13. 车队管理
14. 同业分销门户
15. 移动端（导游报账/百推）

### 第四期（增强）
16. 小程序商城
17. 短信平台
18. BI 决策分析
