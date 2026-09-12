# TDS-数据模型设计

> 文档编号：TDS-DATA-001
> 版本：v1.0
> 日期：2026-09-12
> 状态：初稿
> 依据：易途系统表单字段文档（27张表/180,076条记录）、Odoo功能映射方案

---

## 一、核心实体关系（ER 图）

```
┌──────────────────┐         ┌──────────────────────┐
│  tour.line.type  │         │    product.template   │
│  (线路分类)       │◄────────│    (Odoo 产品基类)    │
│  树形结构         │         └──────────┬───────────┘
└──────────────────┘                    │ 1:1 扩展
                                        ▼
┌──────────────────┐         ┌──────────────────────┐
│    tour.line     │────────▶│   tour.departure     │
│    (线路产品)     │  1:N    │   (发团计划)          │
│    82字段映射     │         │   日期/余位/价格      │
└────────┬─────────┘         └──────────────────────┘
         │ 1:N
         ▼
┌──────────────────┐         ┌──────────────────────┐
│    tour.plan     │────────▶│   tour.plan.reg      │
│    (团队订单)     │  1:N    │   (订单报名)          │
│    137字段映射    │         │   77字段映射          │
│    86,925条      │         │   86,753条            │
└────────┬─────────┘         │   MainRegID 并团逻辑  │
         │                   └──────────┬───────────┘
         │ N:1                          │
         ▼                              │
┌──────────────────┐                    │
│   res.partner    │◀───────────────────┘
│   (客户/供应商)   │  客户 + 供应商统一模型
│   117字段映射     │  SupTypeID 区分类型
└──────────────────┘

┌──────────────────┐         ┌──────────────────────┐
│   tour.guide     │         │  fleet.vehicle       │
│   (导游档案)      │         │  (车辆档案)           │
│   64字段映射      │         │  扩展 Odoo Fleet     │
│   2,173条        │         │  49字段映射 / 71条    │
└──────────────────┘         └──────────────────────┘

┌──────────────────┐         ┌──────────────────────┐
│tour.payment.claim│         │  tour.plan.account   │
│  (收款登记)       │◀────────│  (单团核算)           │
│  30字段映射       │  N:1    │  收入/成本/利润        │
└──────────────────┘         └──────────────────────┘
```

---

## 二、核心表设计

### 2.1 tour.line — 线路产品（82 字段 → Odoo 映射）

**模型类型**：`_inherit = 'product.template'`（扩展 Odoo 产品）

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `name` | Char | LineName | 线路名称 |
| `default_code` | Char | LineCode | 线路编号 |
| `active` | Boolean | UseChk | 启用状态 |
| `categ_id` | Many2one | LineTypeID | 线路分类 → product.category |
| `tour_help_code` | Char | HelpCode | 助记码（快速检索） |
| `tour_day_num` | Integer | DayNum | 天数 |
| `tour_valid_day_num` | Integer | ValidDayNum | 有效天数 |
| `tour_send_place` | Char | SendPlace | 出发地 |
| `tour_end_place` | Char | EndPlace | 目的地 |
| `tour_send_traffic` | Char | SendTraffic | 出发交通方式 |
| `tour_end_traffic` | Char | EndTraffic | 返回交通方式 |
| `tour_srv_text` | Html | SrvText | 行程安排（富文本） |
| `tour_remark` | Text | Remark | 备注 |
| `tour_shopping_info` | Text | ShoppingInfo | 购物信息 |
| `tour_self_paid_item` | Text | SelfPaidItem | 自费项目 |
| `tour_warm_hint` | Text | WarmHint | 温馨提示 |
| `tour_fee_include` | Text | FeeInclude | 费用包含 |
| `tour_fee_exclude` | Text | FeeExclude | 费用不含 |
| `tour_adult_price` | Float | AdultPrice | 成人价 |
| `tour_child_price` | Float | ChildPrice | 儿童价 |
| `tour_old_man_price` | Float | OldManPrice | 老人价 |
| `tour_baby_price` | Float | BabyPrice | 婴儿价 |
| `tour_student_price` | Float | StudentPrice | 学生价 |
| `tour_details_rich` | Html | LineDetailsRich | 行程详情（富文本） |
| `tour_feature_rich` | Html | LineFeatureRich | 线路特色（富文本） |
| `tour_attentions` | Text | Attentions | 注意事项 |
| `tour_score` | Float | LineScore | 线路评分 |
| `tour_special_recommendation` | Boolean | SpecialRecommendation | 特别推荐 |
| `tour_is_special` | Boolean | IsSpecial | 是否特殊线路 |
| `tour_is_jw` | Boolean | IsJw | 是否境外 |
| `tour_is_djs` | Boolean | IsDJS | 是否地接社线路 |
| `tour_dj_supplier_id` | Many2one | DJSupplierID | 地接社 → res.partner |
| `tour_guide_share_rate` | Float | Guide_ShareRate | 导游分成比例 |
| `tour_guide_premium` | Float | Guide_Premium | 导游奖金 |
| `tour_from_province` | Char | FromProvince | 出发省份 |
| `tour_from_city` | Char | FromCity | 出发城市 |
| `tour_to_province` | Char | ToProvince | 目的省份 |
| `tour_to_city` | Char | ToCity | 目的城市 |
| `tour_line_kind` | Char | LineKind | 线路类型 |
| `tour_line_camp` | Char | LineCamp | 线路阵营 |
| `tour_group_type` | Char | GroupType | 团队类型 |
| `tour_plan_class` | Char | PlanClass | 计划分类 |
| `tour_keywords` | Char | Keywords | 搜索关键词 |
| `tour_line_marks` | Char | LineMarks | 线路标签 |
| `tour_line_strategy` | Text | LineStrategy | 线路攻略 |
| `tour_audit_chk` | Boolean | AuditChk | 审核状态 |
| `tour_audit_user` | Char | AuditChk_UserName | 审核人 |
| `tour_audit_date` | Datetime | AuditChk_Date | 审核时间 |
| `tour_serials_id` | Char | SerialsID | 系列ID |
| `tour_order_num` | Integer | OrderNum | 排序号 |
| `company_id` | Many2one | OpCmpID | 所属公司 |
| `department_id` | Many2one | OpDptID | 所属部门 |

**关联模型**：
- `tour.line.detail` — 行程明细（第 N 天行程）
- `tour.line.attachment` — 线路附件

---

### 2.2 tour.line.type — 线路分类（25 字段，树形结构）

**模型类型**：`_inherit = 'product.category'`（扩展 Odoo 产品分类）

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `name` | Char | TypeName | 分类名称 |
| `parent_id` | Many2one | ParentID | 父级分类（树形） |
| `child_ids` | One2many | — | 子分类 |
| `tour_type_code` | Char | TypeCode | 分类代码 |
| `tour_type_brief` | Text | TypeBrief | 分类简介 |
| `tour_layer` | Integer | Layer | 层级深度 |
| `tour_price` | Float | Price | 参考价格 |
| `tour_base_price` | Float | BasePrice | 基础价格 |
| `tour_image` | Binary | LineTypeImg | 分类图片 |
| `tour_custom` | Char | Custom | 自定义属性 |
| `tour_catalog` | Char | LineTypeCatalog | 目录分类 |
| `tour_allow_outside_join` | Boolean | AllowOutsideJoin | 允许外部并团 |
| `tour_order_num` | Integer | OrderNum | 排序号 |
| `active` | Boolean | UseChk | 启用状态 |
| `company_id` | Many2one | OpCmpID | 所属公司 |
| `department_id` | Many2one | OpDptID | 所属部门 |

**树形结构说明**：
- 易途 `ParentID` → Odoo `parent_id`（product.category 原生支持树形）
- `Layer` 字段记录层级深度，用于前端缩进展示
- 实际数据 85 条，典型 3-4 层结构

---

### 2.3 tour.plan — 团队订单（137 字段 → Odoo 映射）

**模型类型**：独立模型（非 sale.order 扩展，业务差异大）

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `name` | Char | PlanCode | 团号（唯一） |
| `plan_name` | Char | PlanName | 计划名称 |
| `line_id` | Many2one | LineID | 线路 → tour.line |
| `plan_type` | Selection | PlanType | 计划类型（DT/DS/ZT/ZS/DD...） |
| `plan_class` | Char | PlanClass | 计划分类 |
| `biz_mode` | Selection | BizMode | 业务模式（12种） |
| `from_type` | Selection | FromType | 订单来源（NB/MS/TH/LZ） |
| `state` | Selection | State | 状态（草稿/确认/出行/完成/取消） |
| `order_state` | Selection | OrderState | 订单状态 |
| `begin_date` | Date | BeginDate | 出发日期 |
| `end_date` | Date | EndDate | 返回日期 |
| `plan_begin_date` | Date | PlanBeginDate | 计划开始日期 |
| `plan_end_date` | Date | PlanEndDate | 计划结束日期 |
| `main_begin_date` | Date | MainBeginDate | 主团开始日期 |
| `main_end_date` | Date | MainEndDate | 主团结束日期 |
| **人数统计** | | | |
| `sum_adult_num` | Integer | SumAdultNum | 成人数合计 |
| `sum_child_num` | Integer | SumChildNum | 儿童数合计 |
| `sum_oldman_num` | Integer | SumOldmanNum | 老人数合计 |
| `sum_baby_num` | Integer | SumBabyNum | 婴儿数合计 |
| `sum_guide_num` | Integer | SumGuideNum | 导游数合计 |
| `sum_student_num` | Integer | SumStudentNum | 学生数合计 |
| `guest_count` | Integer | GuestCount | 客人数 |
| `plan_num` | Integer | PlanNum | 团队人数 |
| **财务汇总** | | | |
| `out_price_quo_sum` | Float | outPrice_QuoSum | 报价总额 |
| `in_com_quo_sum` | Float | InCom_QuoSum | 收入总额 |
| `in_come_change` | Float | InCome_Change | 收入变更 |
| `sum_pay_normal` | Float | SumPay_Normal | 正常收款 |
| `sum_money_delegate` | Float | SumMoney_Delegate | 代收款金额 |
| `sum_pay_delegate` | Float | SumPay_Delegate | 代收款已收 |
| `sum_un_pay` | Float | SumUnPay | 未收款 |
| `sum_money_return` | Float | SumMoney_Return | 退款金额 |
| `sum_pay_return` | Float | SumPay_Return | 退款已付 |
| `sum_deposit` | Float | SumDeposit | 押金 |
| `sum_pay` | Float | SumPay | 已收合计 |
| `un_pay_apply` | Float | UnPay_Apply | 待审批未收 |
| `apply_pay_money` | Float | ApplyPayMoney | 申请付款金额 |
| **核算字段** | | | |
| `in_sum` | Float | InSum | 收入合计 |
| `out_sum` | Float | OutSum | 成本合计 |
| `profit` | Float | Profit | 利润 |
| `in_sum_no_shop` | Float | InSum_NoShop | 收入（不含购物） |
| `out_sum_no_shop` | Float | OutSum_NoShop | 成本（不含购物） |
| `profit_no_shop` | Float | Profit_NoShop | 利润（不含购物） |
| `sys_service_fee` | Float | SysServiceFee | 系统服务费 |
| `exchange_rate` | Float | ExchangeRate | 汇率 |
| `currency` | Char | Currency | 币种 |
| **客人信息** | | | |
| `guest_contact` | Char | GuestContact | 客人联系人 |
| `guest_occupation` | Char | GuestOccupation | 客人职业 |
| `nation` | Char | Nation | 民族 |
| `province` | Char | Province | 省份 |
| `city_name` | Char | CityName | 城市 |
| `receive_place` | Char | ReceivePlace | 接站地点 |
| `receive_traffic` | Char | ReceiveTraffic | 接站交通 |
| `receive_tag` | Char | ReceiveTag | 接站标识 |
| `left_place` | Char | LeftPlace | 送站地点 |
| `left_traffic` | Char | LeftTraffic | 送站交通 |
| **酒店房型** | | | |
| `hotel_star` | Char | HotelStar | 酒店星级 |
| `hotel_day_num` | Integer | HotelDayNum | 酒店天数 |
| `hotel_room_single` | Integer | HotelRoom_Single | 单人间 |
| `hotel_room_standard` | Integer | HotelRoom_Standard | 标准间 |
| `hotel_room_triangle` | Integer | HotelRoom_Triangle | 三人间 |
| `hotel_room_accompany` | Integer | HotelRoom_Accompany | 陪同房 |
| `hotel_room_additional` | Integer | HotelRoom_Additional | 加床 |
| **审核/状态** | | | |
| `audit_chk` | Boolean | AuditChk | 审核状态 |
| `verify_chk` | Boolean | VerifyChk | 验证状态 |
| `verify_date` | Datetime | VerifyDate | 验证时间 |
| `verify_user` | Char | VerifyUser | 验证人 |
| `verify_brief` | Text | VerifyBrief | 验证说明 |
| `op_state_chk` | Boolean | OpStateChk | 操作状态 |
| `zts_confirm_chk` | Boolean | ZTSConfirmChk | 组团社确认 |
| `gather_chk` | Boolean | GatherChk | 汇总状态 |
| `out_state` | Char | OutState | 出团状态 |
| `in_state` | Char | InState | 回团状态 |
| **并团关联** | | | |
| `first_plan_id` | Many2one | FirstPlanID | 原始团队 |
| `main_reg_id` | Many2one | — | 主报名（并团） |
| **其他** | | | |
| `supplier_id` | Many2one | SupplierID | 客户 → res.partner |
| `supplier_name` | Char | SupplierName | 客户名称（冗余） |
| `supplier_user` | Char | SupplierUser | 客户联系人 |
| `supplier_user_mobile` | Char | SupplierUserMobile | 客户手机 |
| `channel_id` | Char | ChannelID | 渠道ID |
| `channel_name` | Char | ChannelName | 渠道名称 |
| `sales_name` | Char | SalesName | 销售人员 |
| `guide_contact` | Char | GuideContact | 导游联系方式 |
| `guide_list` | Text | guidelist | 导游列表 |
| `contract_no` | Char | ContractNo | 合同号 |
| `is_contract` | Boolean | IsContract | 是否签合同 |
| `is_received_guest` | Boolean | IsReceivedGuest | 是否已接客人 |
| `is_d_safe` | Boolean | IsDSafe | 是否安全 |
| `invoice_money` | Float | InvoiceMoney | 开票金额 |
| `un_invoice_money` | Float | UnInvoiceMoney | 未开票金额 |
| `plan_remark` | Text | PlanRemark | 团队备注 |
| `plan_other_remark` | Text | PlanOtherRemark | 其他备注 |
| `special_explain` | Text | SpecialExplain | 特别说明 |
| `order_date` | Date | OrderDate | 下单日期 |
| `reg_order_type` | Char | RegOrderType | 报名订单类型 |
| `actual_shuttle_time` | Char | ActualShuttleTime | 实际接送时间 |
| `company_id` | Many2one | OpCmpID | 所属公司 |
| `department_id` | Many2one | OpDptID | 所属部门 |
| `user_id` | Many2one | OpUserID | 操作员 |
| `write_date` | Datetime | OpDate | 最后操作时间 |

**业务模式枚举（12种）**：

| 代号 | 模式 | tour.plan.plan_type |
|------|------|---------------------|
| DT (1,2) | 团队输单 | `dt` |
| DSK (12) | 团期计划 | `dsk` |
| DSS (13) | 散客单组 | `dss` |
| DSN (14,15) | 散客并团 | `dsn` |
| 流转 (16) | 内部流转 | `lz` |
| 产品计划 (17) | 发布线路协议 | `pp` |
| 关键字并团 (18) | 关键字并团 | `key` |
| DTO (21) | 组团团队 | `dto` |
| DSO (31) | 组团散客 | `dso` |
| DD (41) | 代订项目 | `dd` |
| 自由行 (51,52) | 自由行 | `freedom` |
| 共享协议 (71) | 共享协议 | `share` |

---

### 2.4 tour.plan.reg — 订单报名（77 字段，含并团逻辑）

**模型类型**：独立模型

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `name` | Char | RegCode | 报名单号 |
| `plan_id` | Many2one | — | 所属团队 → tour.plan |
| `line_id` | Many2one | LineID | 线路 → tour.line |
| `plan_name` | Char | PlanName | 计划名称（冗余） |
| `plan_class` | Char | PlanClass | 计划分类 |
| `plan_type` | Selection | PlanType | 计划类型 |
| `biz_mode` | Selection | BizMode | 业务模式 |
| `from_type` | Selection | FromType | 订单来源 |
| **并团核心字段** | | | |
| `main_reg_id` | Many2one | MainRegID | 主报名ID（并团关联） |
| `main_reg_code` | Char | MainRegCode | 主报名单号 |
| `plan_id_main_reg` | Many2one | PlanID_MainReg | 主报名所属团队 |
| `first_plan_id` | Many2one | FirstPlanID | 原始团队 |
| **人数** | | | |
| `guest_count` | Integer | GuestCount | 客人数 |
| `adult_num` | Integer | AdultNum | 成人数 |
| `child_num` | Integer | ChildNum | 儿童数 |
| `old_man_num` | Integer | OldManNum | 老人数 |
| `baby_num` | Integer | BabyNum | 婴儿数 |
| `student_num` | Integer | StudentNum | 学生数 |
| `guide_num` | Integer | GuideNum | 导游数 |
| **日期** | | | |
| `begin_date` | Date | BeginDate | 出发日期 |
| `end_date` | Date | EndDate | 返回日期 |
| `order_date` | Date | OrderDate | 下单日期 |
| `hotel_day_num` | Integer | HotelDayNum | 酒店天数 |
| **客户信息** | | | |
| `supplier_id` | Many2one | SupplierID | 客户 → res.partner |
| `supplier_name` | Char | SupplierName | 客户名称 |
| `supplier_user` | Char | SupplierUser | 联系人 |
| `supplier_user_tel` | Char | SupplierUserTel | 电话 |
| `supplier_user_mobile` | Char | SupplierUserMobile | 手机 |
| `supplier_user_fax` | Char | SupplierUserFax | 传真 |
| `contract_no` | Char | ContractNo | 合同号 |
| `out_code` | Char | OutCode | 外部编码 |
| **交通/地点** | | | |
| `receive_place` | Char | ReceivePlace | 接站地点 |
| `receive_traffic` | Char | ReceiveTraffic | 接站交通 |
| `receive_tag` | Char | ReceiveTag | 接站标识 |
| `left_place` | Char | LeftPlace | 送站地点 |
| `left_traffic` | Char | LeftTraffic | 送站交通 |
| `actual_shuttle_time` | Char | ActualShuttleTime | 实际接送时间 |
| **酒店房型** | | | |
| `hotel_star` | Char | HotelStar | 酒店星级 |
| `hotel_room_single` | Integer | HotelRoom_Single | 单人间 |
| `hotel_room_standard` | Integer | HotelRoom_Standard | 标准间 |
| `hotel_room_triangle` | Integer | HotelRoom_Triangle | 三人间 |
| `hotel_room_accompany` | Integer | HotelRoom_Accompany | 陪同房 |
| `hotel_room_additional` | Integer | HotelRoom_Additional | 加床 |
| **财务** | | | |
| `out_price_quo_sum` | Float | outPrice_QuoSum | 报价总额 |
| `in_com_quo_sum` | Float | InCom_QuoSum | 收入总额 |
| `pre_price_quo_sum` | Float | PrePrice_QuoSum | 预付报价 |
| `pre_cost_quo_sum` | Float | PreCost_QuoSum | 预付成本 |
| `sum_pay_normal` | Float | SumPay_Normal | 正常收款 |
| `sum_un_pay` | Float | SumUnPay | 未收款 |
| `sum_money_delegate` | Float | SumMoney_Delegate | 代收款金额 |
| `sum_pay_delegate` | Float | SumPay_Delegate | 代收款已收 |
| `sum_money_return` | Float | SumMoney_Return | 退款金额 |
| `sum_pay_return` | Float | SumPay_Return | 退款已付 |
| **状态/审核** | | | |
| `gather_chk` | Boolean | GatherChk | 汇总状态 |
| `out_state` | Char | OutState | 出团状态 |
| `in_state` | Char | InState | 回团状态 |
| `reg_verification_chk` | Boolean | RegVerificationChk | 报名验证 |
| `audit_chk0` | Boolean | AuditChk0 | 初审 |
| `audit_chk` | Boolean | AuditChk | 终审 |
| `verify_chk` | Boolean | VerifyChk | 验证 |
| `verify_date` | Datetime | VerifyDate | 验证时间 |
| **其他** | | | |
| `guest_occupation` | Char | GuestOccupation | 客人职业 |
| `nation` | Char | Nation | 民族 |
| `province` | Char | Province | 省份 |
| `city_name` | Char | CityName | 城市 |
| `remark` | Text | Remark | 备注 |
| `sales_name` | Char | SalesName | 销售人员 |
| `company_id` | Many2one | OpCmpID | 所属公司 |
| `department_id` | Many2one | OpDptID | 所属部门 |
| `user_id` | Many2one | OpUserID | 操作员 |

**并团逻辑说明**：
```
并团场景：多个报名单合并到一个主团队

tour.plan.reg (报名单A)  ──main_reg_id──▶  tour.plan.reg (主报名单M)
tour.plan.reg (报名单B)  ──main_reg_id──▶  tour.plan.reg (主报名单M)
tour.plan.reg (报名单C)  ──main_reg_id──▶  tour.plan.reg (主报名单M)

主报名单 M 关联的 tour.plan 即为并团后的目标团队
MainRegID = 0 表示非并团（独立报名）
MainRegID > 0 表示已并团到该报名单
```

---

### 2.5 tour.guide — 导游档案（64 字段）

**模型类型**：独立模型（关联 res.partner 但独立管理）

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `name` | Char | GuideName | 导游姓名 |
| `partner_id` | Many2one | SupID | 关联联系人 → res.partner |
| `guide_code` | Char | GuideCode | 导游证号 |
| `help_code` | Char | HelpCode | 助记码 |
| `sex` | Selection | Sex | 性别 |
| `nation` | Char | Nation | 民族 |
| `born_place` | Char | BornPlace | 出生地 |
| `edu` | Char | Edu | 学历 |
| `id_num` | Char | IDNum | 身份证号 |
| `tel` | Char | Tel | 电话 |
| `mobile` | Char | Mobile | 手机 |
| `zip_code` | Char | ZipCode | 邮编 |
| `addr` | Char | Addr | 地址 |
| `photo` | Binary | Photo | 照片 |
| `remark` | Text | Remark | 备注 |
| `language` | Char | LanguageName | 语言能力 |
| `licence` | Char | Licence | 执照 |
| `licence_type` | Char | LicenceType | 执照类型 |
| `guide_type` | Char | GuideType | 导游类型 |
| `guide_leader` | Boolean | GuideLeader | 是否领队 |
| `is_tour_guide` | Boolean | IsTourGuide | 是否导游 |
| `is_driver_guide` | Boolean | IsDriverGuide | 是否司机兼导游 |
| `guide_lead_type` | Char | GuideLeadType | 带团类型 |
| `guide_account` | Char | GuideAccount | 登录账号 |
| `job_no` | Char | JobNo | 工号 |
| `marital_status` | Char | MaritalStatus | 婚姻状况 |
| `entry_time` | Date | EntryTme | 入职时间 |
| `working_date` | Date | WorkingDate | 工作年限起算 |
| `career_years` | Integer | CareerYears | 从业年限 |
| `guide_group` | Char | GuideGroup | 导游分组 |
| `group_type` | Char | GroupType | 团队类型偏好 |
| `shop_type` | Char | ShopType | 购物店类型偏好 |
| `guide_advantage` | Text | GuideAdvantage | 导游优势 |
| `guide_star` | Float | GuideStar | 导游星级 |
| `grade` | Char | Grade | 等级 |
| `recommend_class` | Char | RecommendClass | 推荐等级 |
| `area` | Char | Area | 服务区域 |
| `birthday` | Date | Birthday | 生日 |
| **银行信息** | | | |
| `account_bank` | Char | AccountBank | 开户行 |
| `account_name` | Char | AccountName | 账户名称 |
| `account_no` | Char | AccountNo | 银行账号 |
| `loan_rate` | Float | LoanRate | 借款利率 |
| **司机兼导游字段** | | | |
| `driver_licence` | Char | DriverLicence | 驾照号 |
| `driver_seat_num` | Integer | DriverSeatNum | 座位数 |
| `driver_car_type` | Char | DriverCarType | 车型 |
| `driver_car_name` | Char | DriverCarName | 车辆名称 |
| **审核/状态** | | | |
| `active` | Boolean | UseChk | 启用状态 |
| `audit_chk` | Boolean | CmpAuditChk | 审核状态 |
| `audit_user` | Char | CmpAuditChk_UserName | 审核人 |
| `audit_brief` | Text | CmpAuditChk_Brief | 审核说明 |
| `audit_date` | Datetime | CmpAuditChk_Date | 审核时间 |
| `company_id` | Many2one | OpCmpID | 所属公司 |
| `department_id` | Many2one | OpDptID | 所属部门 |

---

### 2.6 fleet.vehicle 扩展 — 车辆档案（49 字段）

**模型类型**：`_inherit = 'fleet.vehicle'`（扩展 Odoo Fleet 模块）

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `tour_driver_name` | Char | DriverName | 司机姓名 |
| `tour_driver_code` | Char | DriverCode | 司机编码 |
| `tour_help_code` | Char | HelpCode | 助记码 |
| `tour_sex` | Selection | Sex | 性别 |
| `tour_nation` | Char | Nation | 民族 |
| `tour_born_place` | Char | BornPlace | 出生地 |
| `tour_edu` | Char | Edu | 学历 |
| `tour_id_num` | Char | IDNum | 身份证号 |
| `tour_age` | Integer | Age | 年龄 |
| `tour_tel` | Char | Tel | 电话 |
| `tour_mobile` | Char | Mobile | 手机 |
| `tour_zip_code` | Char | ZipCode | 邮编 |
| `tour_addr` | Char | Addr | 地址 |
| `tour_photo` | Binary | Photo | 照片 |
| `tour_photo2` | Binary | Photo2 | 照片2 |
| `tour_remark` | Text | Remark | 备注 |
| `tour_licence` | Char | Licence | 车牌号 |
| `tour_licence_date` | Date | LicenceDate | 驾照日期 |
| `tour_licence_type` | Char | LicenceType | 驾照类型 |
| `tour_buy_date` | Date | BuyDate | 购车日期 |
| `seat_num` | Integer | SeatNum | 座位数 |
| `car_type` | Char | CarType | 车型 |
| `tour_is_autarky` | Boolean | IsAutarky | 是否自营 |
| `tour_loan_rate` | Float | LoanRate | 借款利率 |
| `tour_opening_bank` | Char | Openingbank | 开户行 |
| `tour_bank_account` | Char | BankAccount | 银行账号 |
| `tour_supplier_id` | Many2one | SupplierID | 车辆公司 → res.partner |
| `tour_supplier_name` | Char | SupplierName | 车辆公司名称 |
| `tour_active` | Boolean | UseChk | 启用状态 |
| `tour_audit_chk` | Boolean | AuditChk | 审核状态 |
| `company_id` | Many2one | OpCmpID | 所属公司 |
| `department_id` | Many2one | OpDptID | 所属部门 |

---

### 2.7 tour.payment.claim — 收款登记（30 字段）

**模型类型**：独立模型（关联 account.payment 但独立管理）

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `name` | Char | PayClaimID | 收款登记ID |
| `payee_id` | Many2one | PayeeID | 收款人 |
| `payee` | Char | Payee | 收款人名称 |
| `is_main_reg` | Boolean | IsMainReg | 是否主报名 |
| `supplier_id` | Many2one | SupplierID | 客户 → res.partner |
| `supplier_name` | Char | SupplierName | 客户名称 |
| `pay_date` | Date | PayDate | 付款日期 |
| `pay_money` | Float | PayMoney | 付款金额 |
| `use_money` | Float | UseMoney | 已使用金额 |
| `balance_money` | Float | BalanceMoney | 余额 |
| `account_id` | Many2one | AccountID | 银行账户 |
| `bank_name_pay` | Char | BankName_Pay | 付款银行 |
| `account_name_pay` | Char | AccountName_Pay | 付款账户名 |
| `account_no_pay` | Char | AccountNo_Pay | 付款账号 |
| `pay_type` | Selection | PayType | 付款方式 |
| `brief` | Text | Brief | 摘要 |
| `claim_state` | Selection | ClaimState | 认领状态 |
| `tax_code` | Char | TaxCode | 税号 |
| `trans_fee_rate` | Float | TransFeeRate | 手续费率 |
| `trans_fee` | Float | TransFee | 手续费 |
| `star_state` | Char | StarState | 星标状态 |
| `company_id` | Many2one | OpCmpID | 所属公司 |
| `department_id` | Many2one | OpDptID | 所属部门 |

---

### 2.8 res.partner 扩展 — 供应商（117 字段 → Odoo 映射）

**模型类型**：`_inherit = 'res.partner'`（扩展 Odoo 联系人）

易途系统中 10 种供应商类型（客户、地接社、酒店、餐厅、车辆公司、票务公司、景区、购物店、保险公司、自费公司）共享 117 个字段，通过 `SupTypeID` 区分。

**Odoo 映射策略**：统一使用 `res.partner`，通过 `category_id`（联系人标签）区分供应商类型。

| Odoo 字段 | 类型 | 易途字段 | 说明 |
|-----------|------|---------|------|
| `name` | Char | CmpName | 公司名称 |
| `ref` | Char | CmpCode | 公司代码 |
| `tour_help_code` | Char | HelpCode | 助记码 |
| `phone` | Char | CmpTel | 电话 |
| `mobile` | Char | CmpManagerMobile | 负责人手机 |
| `fax` | Char | CmpFax | 传真 |
| `zip` | Char | CmpZip | 邮编 |
| `street` | Char | CmpAddr | 地址 |
| `street2` | Char | CmpAddr2 | 地址2 |
| `state_id` | Many2one | Province | 省份 → res.country.state |
| `city` | Char | CityName | 城市 |
| `zone` | Char | Zone | 区域 |
| `county_town` | Char | CountyTown | 县镇 |
| `tour_manager` | Char | CmpManager | 负责人 |
| `tour_manager_id_code` | Char | CmpManagerIDCode | 负责人证件号 |
| `tour_boss_birthday` | Date | BossBirthday | 负责人生日 |
| `tour_bank` | Char | CmpBank | 开户行 |
| `tour_account` | Char | CmpAccount | 账户名 |
| `tour_account_no` | Char | CmpAccountNo | 银行账号 |
| `tour_remark` | Text | Remark | 备注 |
| `tour_remark2` | Text | Remark2 | 备注2 |
| `active` | Boolean | UseChk | 启用状态 |
| **合同信息** | | | |
| `tour_contract_no` | Char | ContractNo | 合同号 |
| `tour_contract_number` | Char | ContractNumber | 合同编号 |
| `tour_contract_date` | Date | ContractDate | 合同日期 |
| `tour_contract_begin` | Date | ContractBeginDate | 合同开始日期 |
| `tour_contract_end` | Date | ContractEndDate | 合同结束日期 |
| `tour_is_contract` | Boolean | IsContract | 是否签合同 |
| `tour_cooperation_agreement` | Binary | CooperationAgreement | 合作协议附件 |
| **财务信息** | | | |
| `tour_credit_limit` | Float | CreditLmt | 信用额度 |
| `tour_credit_limit_type` | Char | CreditLmtType | 额度类型 |
| `tour_credit_limit_sk` | Float | CreditLmt_SK | 收款信用额度 |
| `tour_free_payment_limit` | Float | FreePaymentLmt | 免审付款额度 |
| `tour_tax_payer_no` | Char | TaxPayerNo | 纳税识别号 |
| `tour_invoice_title` | Char | InvoiceTitle | 发票抬头 |
| `tour_is_invoice` | Boolean | IsInvoice | 是否开票 |
| `tour_invoice_rule` | Char | Invoice_Rule | 开票规则 |
| `tour_charge_period` | Char | ChargePeriod | 结算周期 |
| `tour_pay_way` | Char | PayWay | 结算方式 |
| `tour_finance_sys_chk` | Boolean | FinaceSysChk | 财务系统权限 |
| `tour_allow_login_fin_sys` | Boolean | AllowLoginFinSys | 允许登录财务系统 |
| **服务信息** | | | |
| `tour_service_type` | Char | ServiceType | 服务类型 |
| `tour_service_price` | Float | ServicePrice | 服务价格 |
| `tour_service_calc_mode` | Char | ServiceCalcMode | 服务计算方式 |
| `tour_service_fee_round_way` | Char | ServiceFeeRoundWay | 服务费取整方式 |
| `tour_agr_price` | Boolean | AgrPrice | 协议价 |
| `tour_any_price` | Boolean | AnyPrice | 任意价 |
| `tour_grade` | Char | Grade | 等级 |
| `tour_level_id` | Char | LevelID | 级别ID |
| `tour_level_name` | Char | LevelName | 级别名称 |
| **微信/支付宝** | | | |
| `tour_merchant_ids` | Char | MerchantIds | 商户号 |
| `tour_wx_logo` | Binary | WxLogo | 微信Logo |
| `tour_wx_licence` | Binary | WxLicence | 微信营业执照 |
| `tour_alipay_identity` | Char | AliPayIdentity | 支付宝身份 |
| `tour_alipay_book_identity` | Char | AliPayBookIdentity | 支付宝账本身份 |
| **审核** | | | |
| `tour_audit_chk` | Boolean | CmpAuditChk | 审核状态 |
| `tour_audit_user` | Char | CmpAuditChk_UserName | 审核人 |
| `tour_audit_brief` | Text | CmpAuditChk_Brief | 审核说明 |
| `tour_audit_date` | Datetime | CmpAuditChk_Date | 审核时间 |
| **其他** | | | |
| `tour_channel_id` | Char | ChannelID | 渠道ID |
| `tour_channel_name` | Char | ChannelName | 渠道名称 |
| `tour_buyer_id` | Char | BuyerID | 采购员ID |
| `tour_purchaser` | Char | Purchaser | 采购人 |
| `tour_license_id` | Char | licenseID | 许可证号 |
| `tour_location` | Char | Location | 位置 |
| `tour_room_type` | Char | RoomType | 房型（酒店专用） |
| `tour_latitude` | Float | Latitude | 纬度 |
| `tour_longitude` | Float | Longtitue | 经度 |
| `tour_res_isolation` | Boolean | ResIsolation | 资源隔离 |
| `tour_sort_code` | Integer | SortCode | 排序码 |

**供应商类型标签映射**：

| SupTypeID | 类型 | Odoo category_id 标签 |
|-----------|------|----------------------|
| 1 | 客户 | `tour_customer` |
| 2 | 地接社 | `tour_ditch` |
| 4 | 酒店 | `tour_hotel` |
| 5 | 餐厅 | `tour_restaurant` |
| 6 | 车辆公司 | `tour_vehicle_company` |
| 7 | 票务公司 | `tour_ticket_company` |
| 8 | 景区景点 | `tour_scenic` |
| 9 | 购物店 | `tour_shop` |
| 10 | 保险公司 | `tour_insurance` |
| 11 | 签证公司 | `tour_visa` |
| 13 | 自费公司 | `tour_self_fee` |
| 15 | 平台商 | `tour_platform` |

---

## 三、辅助模型

### 3.1 tour.departure — 发团计划

| Odoo 字段 | 类型 | 说明 |
|-----------|------|------|
| `line_id` | Many2one | 线路 → tour.line |
| `departure_date` | Date | 出发日期 |
| `return_date` | Date | 返回日期 |
| `adult_price` | Float | 成人价 |
| `child_price` | Float | 儿童价 |
| `total_seats` | Integer | 总位数 |
| `sold_seats` | Integer | 已售位数 |
| `remaining_seats` | Integer | 剩余位数（计算字段） |
| `state` | Selection | 状态（计划/收客/满位/已发/取消） |
| `plan_ids` | One2many | 关联团队 → tour.plan |

### 3.2 tour.plan.account — 单团核算

| Odoo 字段 | 类型 | 说明 |
|-----------|------|------|
| `plan_id` | Many2one | 团队 → tour.plan |
| `income_total` | Float | 收入合计 |
| `cost_total` | Float | 成本合计 |
| `profit` | Float | 利润 |
| `income_no_shop` | Float | 收入（不含购物） |
| `cost_no_shop` | Float | 成本（不含购物） |
| `profit_no_shop` | Float | 利润（不含购物） |
| `shop_commission` | Float | 购物佣金 |
| `service_fee` | Float | 服务费 |
| `state` | Selection | 状态（待核算/已核算/已确认） |

### 3.3 基础数据映射

| 易途表单 | Odoo 映射 | 说明 |
|---------|----------|------|
| 结算方式（7条） | `tour.pay.way` 或 `account.payment.method` | PayWayID/PayWayName/PayWayType |
| 业务类型（5条） | `tour.biz.type` (Selection) | ItemID/ItemName |
| 职务（15条） | `hr.job` 或 Selection | ItemID/ItemName |
| 基础数据-类型2/3/5 | `tour.base.item` (通用) | ItemTypeID 区分类型 |
| 部门设置（22条） | `hr.department` | DptID/DptName/ParentID |
| 用户管理（327条） | `res.users` | UserID/UserName/UserAccount |
| 公司信息（7条） | `res.company` | CmpID/CmpName |
| 银行账户（72条） | `res.partner.bank` | AccountID/AccountName/BankName |

---

## 四、索引策略

### 4.1 核心查询索引

```sql
-- tour.plan（86,925 条，高频查询）
CREATE INDEX idx_tour_plan_line ON tour_plan (line_id);
CREATE INDEX idx_tour_plan_state ON tour_plan (state);
CREATE INDEX idx_tour_plan_begin_date ON tour_plan (begin_date);
CREATE INDEX idx_tour_plan_supplier ON tour_plan (supplier_id);
CREATE INDEX idx_tour_plan_company_dept ON tour_plan (company_id, department_id);
CREATE INDEX idx_tour_plan_plan_type ON tour_plan (plan_type);
CREATE INDEX idx_tour_plan_code ON tour_plan (name);  -- 团号唯一索引

-- tour.plan.reg（86,753 条，高频查询）
CREATE INDEX idx_tour_plan_reg_plan ON tour_plan_reg (plan_id);
CREATE INDEX idx_tour_plan_reg_main ON tour_plan_reg (main_reg_id);
CREATE INDEX idx_tour_plan_reg_supplier ON tour_plan_reg (supplier_id);
CREATE INDEX idx_tour_plan_reg_begin_date ON tour_plan_reg (begin_date);
CREATE INDEX idx_tour_plan_reg_line ON tour_plan_reg (line_id);

-- tour.line（212 条，低频但关联多）
CREATE INDEX idx_tour_line_categ ON tour_line (categ_id);
CREATE INDEX idx_tour_line_code ON tour_line (default_code);
CREATE INDEX idx_tour_line_active ON tour_line (active);

-- tour.payment.claim（收款查询）
CREATE INDEX idx_pay_claim_supplier ON tour_payment_claim (supplier_id);
CREATE INDEX idx_pay_claim_date ON tour_payment_claim (pay_date);
CREATE INDEX idx_pay_claim_state ON tour_payment_claim (claim_state);

-- res.partner（供应商查询）
CREATE INDEX idx_partner_tour_category ON res_partner (category_id);
CREATE INDEX idx_partner_tour_help_code ON res_partner (tour_help_code);
```

### 4.2 全文搜索索引

```sql
-- 线路名称/编号搜索
CREATE INDEX idx_tour_line_search ON tour_line
  USING gin(to_tsvector('simple', coalesce(name,'') || ' ' || coalesce(default_code,'') || ' ' || coalesce(tour_help_code,'')));

-- 团队搜索
CREATE INDEX idx_tour_plan_search ON tour_plan
  USING gin(to_tsvector('simple', coalesce(name,'') || ' ' || coalesce(plan_name,'') || ' ' || coalesce(guest_contact,'')));
```

---

## 五、大表分区方案

### 5.1 分区策略

| 表 | 记录数 | 分区键 | 分区方式 | 说明 |
|----|--------|--------|---------|------|
| `tour.plan` | 86,925+ | `begin_date` | 按年 Range | 每年一个分区 |
| `tour.plan.reg` | 86,753+ | `begin_date` | 按年 Range | 与 tour.plan 对齐 |
| `tour.payment.claim` | 51+ | `pay_date` | 按年 Range | 预留增长 |
| `mail.message` | 随业务增长 | `date` | 按月 Range | Odoo 消息日志 |

### 5.2 分区 DDL 示例

```sql
-- tour.plan 按年分区
CREATE TABLE tour_plan (
    id SERIAL,
    begin_date DATE NOT NULL,
    -- ... 其他字段
) PARTITION BY RANGE (begin_date);

CREATE TABLE tour_plan_2024 PARTITION OF tour_plan
  FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE tour_plan_2025 PARTITION OF tour_plan
  FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE tour_plan_2026 PARTITION OF tour_plan
  FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- 自动创建未来分区（pg_cron 或 Odoo cron）
-- 每年 12 月自动创建下一年分区
```

### 5.3 分区注意事项

1. **Odoo ORM 兼容性**：Odoo ORM 不原生支持分区表，需要在 SQL 层面创建分区，ORM 层面透明访问
2. **主键约束**：分区表的主键必须包含分区键，建议使用 `(id, begin_date)` 复合主键
3. **外键约束**：PostgreSQL 分区表的外键在 PostgreSQL 12+ 支持
4. **索引**：分区表的索引自动应用到所有子分区

---

## 六、数据迁移映射

### 6.1 迁移优先级

| 优先级 | 表 | 记录数 | 依赖 |
|--------|-----|--------|------|
| P0 | res.company（公司信息） | 7 | 无 |
| P0 | res.partner（供应商） | 4,122 | res.company |
| P0 | tour.line.type（线路分类） | 85 | 无 |
| P1 | tour.line（线路产品） | 212 | tour.line.type |
| P1 | tour.guide（导游档案） | 2,173 | res.partner |
| P1 | fleet.vehicle（车辆档案） | 71 | res.partner |
| P2 | tour.plan（团队订单） | 86,925 | tour.line, res.partner |
| P2 | tour.plan.reg（订单报名） | 86,753 | tour.plan |
| P3 | tour.payment.claim（收款登记） | 51 | res.partner |
| P3 | res.partner.bank（银行账户） | 72 | res.partner |
| P4 | 基础数据（结算方式/业务类型等） | 34 | 无 |
| P4 | hr.department（部门） | 22 | res.company |
| P4 | res.users（用户） | 327 | hr.department |

### 6.2 数据量预估

| 指标 | 当前值 | 1年预估 | 3年预估 |
|------|--------|---------|---------|
| tour.plan | 86,925 | 120,000 | 200,000 |
| tour.plan.reg | 86,753 | 120,000 | 200,000 |
| res.partner | 4,122 | 6,000 | 10,000 |
| tour.line | 212 | 500 | 1,000 |
| mail.message | 0 | 500,000 | 2,000,000 |

---

## 附录 A：易途字段 → Odoo 模型完整映射表

| 易途表 | 记录数 | 字段数 | Odoo 模型 | 开发方式 |
|--------|--------|--------|----------|---------|
| 线路产品 | 212 | 82 | tour.line (product.template) | 扩展 |
| 线路分类 | 85 | 25 | tour.line.type (product.category) | 扩展 |
| 客户档案 | 1,335 | 117 | res.partner | 扩展 |
| 地接社档案 | 194 | 117 | res.partner + category | 扩展 |
| 酒店档案 | 886 | 117 | res.partner + category | 扩展 |
| 餐厅档案 | 240 | 117 | res.partner + category | 扩展 |
| 车辆公司 | 137 | 117 | res.partner + category | 扩展 |
| 票务公司 | 9 | 117 | res.partner + category | 扩展 |
| 景区景点 | 337 | 117 | res.partner + category | 扩展 |
| 购物店 | 77 | 117 | res.partner + category | 扩展 |
| 保险公司 | 6 | 117 | res.partner + category | 扩展 |
| 自费公司 | 121 | 117 | res.partner + category | 扩展 |
| 导游档案 | 2,173 | 64 | tour.guide | 新建 |
| 车辆档案 | 71 | 49 | fleet.vehicle | 扩展 |
| 团队订单 | 86,925 | 137 | tour.plan | 新建 |
| 订单报名 | 86,753 | 77 | tour.plan.reg | 新建 |
| 收款登记 | 51 | 30 | tour.payment.claim | 新建 |
| 银行账户 | 72 | 23 | res.partner.bank | 扩展 |
| 结算方式 | 7 | 6 | tour.pay.way | 新建 |
| 部门设置 | 22 | 23 | hr.department | 扩展 |
| 用户管理 | 327 | 53 | res.users | 扩展 |
| 公司信息 | 7 | 117 | res.company | 扩展 |
| 基础数据(×5) | 29 | 17 | tour.base.item | 新建 |
