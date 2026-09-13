# tour_agency 模块参考分析

> 来源：https://apps.odoo.com/apps/modules/18.0/tour_agency
> 下载：/home/adai/tms/a-调研/第三方参考/tour_agency/（zip 已解压，源 zip 为 tour_agency.zip，1.5MB）

## 一、模块概览

| 项 | 值 |
|---|---|
| 名称 | Tours and Travel Management System - All in one (with Portal) |
| 技术名 | tour_agency |
| 作者 | Cyshield（埃及） |
| 版本 | 18.0.1.0.0（Odoo 18，TMS 用 19，仅作参考） |
| 许可 | LGPL-3 |
| 代码量 | 6729 行 |
| 依赖 | base/web/website/portal/crm/sale_management/account/calendar/contacts/mail/hr/purchase/payment/website_payment/website_sale |

定位：B2C 在线旅行社一站式系统（官网预订 + CRM + 销售 + 门户），与 TMS（B2B 组团社、并团/单团核算）业务模型不同，但其「预订状态机 + 销售/财务对接 + 门户」的技术实现有直接借鉴价值。

## 二、模型清单

### 独立模型（12 主 + 6 子）
| 模型 | 说明 |
|---|---|
| tour.package | 线路产品（继承 mail.thread/website.seo.metadata/website.published.mixin） |
| tour.package.image/category/tag/inclusion/exclusion | 线路图片/分类/标签/包含项/排除项 |
| tour.booking | **预订（核心，1400 行）** |
| tour.passenger | 乘客（姓名/证件/紧急联系人/特殊需求） |
| tour.itinerary | 行程（day-by-day） |
| tour.hotel / tour.hotel.room.type / tour.hotel.amenity | 酒店/房型/设施 |
| tour.transportation | 交通（车型/司机） |
| tour.meal | 餐饮 |
| tour.attraction | 景点 |
| tour.inquiry | 询价线索（CRM 前置） |
| tour.expense | 费用（挂在 booking 上） |

### 继承模型（7 个 _inherit，财务对接核心）
| 继承 | 用途 |
|---|---|
| sale.order | 预订生成销售单，confirm/cancel 联动 |
| account.move | 发票/凭证扩展 |
| account.payment | 支付扩展（关联 booking） |
| crm.lead | 询价转线索 |
| calendar.event | 行程排期 |
| res.partner | 客户扩展 |
| res.company / res.config.settings | 代理配置 |

## 三、核心设计模式

### 1. 预订状态机（tour.booking.state）
```
draft → confirmed → in_progress → completed
                          └→ cancel
```
- action_confirm：确认预订，若有关联 SO 且为 draft 则 action_confirm()
- action_start / action_complete：complete 时若 SO 存在且未开票则 _create_invoice_from_sale_order()
- action_cancel：取消，联动 SO.action_cancel() + 作废 draft 发票

### 2. 支付状态机（payment_status）
```
unpaid → partially_paid → paid
                          └→ refunded
```
- 从 payment_ids.state / invoice_ids.payment_state / amount_paid 派生（compute+store）
- 金额：direct_paid（直接支付）+ invoice_paid（从 SO 发票的 amount_total - amount_residual 累加）
- 多币种转换用 currency_id._convert

### 3. 财务对接链路（关键借鉴点）
```
tour.booking ──sale_order_id──> sale.order ──> account.move(invoice)
     └── direct_invoice_ids ──> account.move
     └── payment_ids ──> account.payment (继承)
```
- booking 既可走 sale.order 出票，也可直接挂 direct_invoice_ids
- invoice_ids 是 compute（= direct_invoice_ids ∪ sale_order_id.invoice_ids）
- amount_paid 统一从 posted 发票的 amount_total - amount_residual 派生，避免双写

### 4. 门户（portal.mixin + access_token）
- tour.booking 继承 portal.mixin，access_token 字段
- controllers/portal.py：旅客自助查看预订/下载行程/跟踪支付

### 5. 官网预订（website 系列）
- controllers/main.py：官网预订流程（选线路 → 填乘客 → 下单）
- views/website_*.xml + tour_booking_wizard：前端预订向导
- data/website_menu_data.xml：网站菜单

## 四、对 TMS 的可借鉴点

| tour_agency 做法 | TMS 现状 | 借鉴建议 |
|---|---|---|
| portal.mixin + access_token 做旅客门户 | 未做门户（小程序 API 暂缓） | 后续 tour_api/门户可复用此模式 |
| payment_status 从发票 amount_residual 派生 | 收款走 account.move，金额自派生 | 已一致，可对照其多币种转换写法 |
| booking → sale.order 全自动联动 | 独立 tour.plan + 手动 account.move | 保留 TMS 方案（并团/单团核算需独立模型）；仅参考其 SO 状态联动 |
| itinerary PDF report（行程单） | tour_report 待做 | 直接参考 report/tour_itinerary_report.xml 的 PDF 版式 |
| email_template_data.xml（23KB 邮件模板） | 未做通知 | 参考邮件模板结构（预订确认/提醒/完成通知） |
| 支付状态机四态 + 派生逻辑 | 收款认领状态机已自研 | 参考其 unpaid/partial/paid/refunded 派生口径 |
| website 预订 snippet | 不做官网 | 跳过 |

## 五、结论

tour_agency 是标准 B2C 在线旅行社（官网+门户+CRM+销售），与 TMS 的 B2B 组团业务（并团、单团核算、10 类对账、佣金个税、差额征税）在业务层不重叠，TMS 的财务合规深度远超它。**最有价值的参考项是：itinerary PDF 版式、门户 access_token 模式、支付状态派生口径、邮件模板结构**——这四项可直接用于后续 tour_report / tour_api / 通知功能，避免从零造轮子。
