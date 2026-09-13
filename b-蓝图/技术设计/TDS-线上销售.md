# TDS-线上销售（B2C 散客线上报名）

> 文档编号：TDS-B2C-001
> 版本：v1.0
> 日期：2026-09-13
> 状态：初稿
> 依据：BS-01 线路管理、BS-02 订单管理、TDS-模块划分、TDS-系统架构设计、现有代码 tour_product / tour_order

---

## 一、需求范围与设计目标

### 1.1 最小闭环边界

B2C 散客线上销售，**只做「展示 + 报名」，线下付款**（不含在线支付、不含购物车、不含订单履约）：

```
游客浏览线路 → 查看详情/班期 → 选发团日期 → 填报名表单 → 提交 → 生成报名记录 → 线下付款/门店确认
```

明确**不做**（避免过度设计，后续模块承接）：
- 在线支付（微信/支付宝）→ 属 `tour_api` + 聚合支付，P2
- 购物车 / 多线路下单 → 属 website_sale 方向，本期不做
- 同业分销 → 属 `tour_b2b`，P2
- 电子合同签署 → 属 `tour_order` 履约深化

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| 复用 | 复用 Odoo 19 `website` / `portal` 标准模块，零前端框架引入 |
| 隔离 | 网站 HTTP/QWeb 逻辑独立成模块，不污染后端业务模型 |
| 简单 | 无登录报名优先，降低转化流失 |
| 闭环 | 报名数据直接落到 `tour.plan.reg`，与后端订单/计调天然打通 |

---

## 二、模块规划

### 2.1 结论：新建 `tour_website` 模块（不扩展 tour_product/tour_order）

**决策理由**：
1. `tour_product`、`tour_order` 是纯后端数据模型，若塞入 controller / QWeb / sitemap，会引入 `website` 依赖，污染底层模块（违反「简单优先」与模块分层）。
2. 与既有分层一致：`tour_base`（基础设施）→ `tour_product` / `tour_order`（业务模型）→ `tour_website`（展示与交互层）。
3. website 层后续可承载更多前台能力（同业门户、微页面、SEO），独立模块便于演进。

### 2.2 依赖关系

```python
# tour_website/__manifest__.py
{
    'name': 'TMS Website - B2C 线上销售',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '线路展示 + 散客在线报名（线下付款）',
    'depends': [
        'base',
        'website',      # 站点/页面/QWeb/sitemap/SEO
        'portal',       # portal 登录 + portal_layout（可选登录查单）
        'tour_base',    # 权限组、加密 mixin、BIZ_MODE 常量
        'tour_product', # tour.line / tour.departure / tour.line.detail
        'tour_order',   # tour.plan / tour.plan.reg
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/templates.xml',        # QWeb 模板
        'views/snippets.xml',         # 可选 website 片段
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

**为何不依赖 `website_sale`**：线下付款，无购物车/在线支付需求。`website_sale` 已安装（容器实测），但本期不调用其功能；后续若上在线支付，再评估复用 `website_sale` 的 cart/checkout 还是走 `tour_api` 聚合支付。

### 2.3 模块目录结构

```
tour_website/
├── __manifest__.py
├── __init__.py
├── controllers/
│   ├── __init__.py
│   ├── main.py          # 线路列表/详情/报名
│   └── portal.py        # (可选) 我的报名
├── models/
│   ├── __init__.py
│   ├── tour_line.py     # 展示辅助字段（website_published 等）
│   └── tour_plan_reg.py # 在线报名创建方法
├── views/
│   ├── templates.xml    # QWeb 页面模板
│   └── assets.xml       # 前端资源（可选）
├── security/
│   └── ir.model.access.csv
└── static/
    └── description/icon.png
```

---

## 三、数据流设计

### 3.1 核心映射关系

现有模型中有两个「发团计划」概念，需在设计层面厘清（这是本方案的关键辨析点）：

| 模型 | 模块 | 职责 | 角色 |
|------|------|------|------|
| `tour.departure` | tour_product | 班期/余位/价格/发布状态（`seats`/`booked_seats`/`remain_seats`/`price_adult`/`price_child`/`state`） | **客人看到的「发团日期」** |
| `tour.plan` | tour_order | 团队订单（`plan_code` 团号/`begin_date`/人数/客户/状态机） | **报名记录的承载团队** |

**结论**：
- 客人在前端看到的「出发日期班期」= `tour.departure`（`state='published'` 且 `remain_seats > 0`）。
- 报名落地时，`tour.plan.reg` 关联到 `tour.plan`（承载团队），并以 `first_plan_id` 记录「首次挂接发团计划」（散客并团核心指针，见 tour_order 代码注释）。

### 3.2 报名数据流（最小闭环）

```
1. 浏览
   GET /tours            → tour.line (active=True, audit_state='approved')
   GET /tours/<id>       → tour.line + tour.line.detail（行程明细）

2. 选班期
   详情页列出 tour.departure (line_id=<line>, state='published', remain_seats>0, start_date>=today)
   → 选中 departure_id

3. 提交报名
   POST /tours/<line_id>/register
   ├─ 校验：departure 有效、余位充足、必填（姓名/手机/人数）、日期合法
   ├─ 查找或创建 tour.plan（团期计划，承载本次报名的团队）
   │     biz_mode='12' (DSK 团期计划) / plan_type='2' (散客散拼)
   │     若同线路同 departure 已有团 → 复用（散客并团 DSN 语义）
   │     否则 → 新建 plan，生成 plan_code（团号）
   ├─ 创建 tour.plan.reg
   │     reg_code 自动生成（报名单号，唯一）
   │     plan_id = 承载团队；first_plan_id = 承载团队
   │     line_id 派生自 plan；begin_date/end_date 来自 departure
   │     supplier_name / supplier_user / supplier_user_mobile（脱敏落盘）
   │     adult_num / child_num / ... = 表单人数
   │     in_com_quo_sum = 按价格体系计算的报价
   │     from_type='1'（内部）/ channel_name='B2C线上'（标记来源）
   └─ 回写余位：tour.departure.booked_seats += 报名人数

4. 反馈
   GET /tours/register/success/<reg_id> → 成功页（展示报名单号，提示线下付款）
```

### 3.3 数据关系图

```
tour.line (线路)
   │ 1:N
   ├──▶ tour.line.detail (行程明细，展示用)
   └──▶ tour.departure (班期/余位/价格，客人选日期)
              │
              │ (按 line+date 定位/创建)
              ▼
        tour.plan (承载团队，DSK 团期计划)
              │ 1:N
              ▼
        tour.plan.reg (报名记录，散客)
              └─ first_plan_id → tour.plan (并团溯源)
              └─ supplier_user_mobile 等 PII 字段（加密落盘）
```

### 3.4 并团语义（本期是否实现）

- **最小闭环**：每个「线路 + 班期」对应一个 `tour.plan`（团期计划 DSK），同班期的散客报名都挂到同一个 plan 上（天然实现「散客并团 DSN」的物理形态）。`first_plan_id` 一律指向该 plan。
- 复杂的「跨班期并团 / 关键字并团 / 变更团」属后端 `tour_order` 已有能力，线上报名**不触发**，由计调在后台操作。本期线上只做「按班期挂团」。

---

## 四、Controller 与路由设计

### 4.1 路由清单

| 方法 | 路由 | auth | 说明 |
|------|------|------|------|
| GET | `/tours` | public | 线路列表页（支持分类/出发城市筛选） |
| GET | `/tours/<int:line_id>` | public | 线路详情页（含班期列表 + 报名入口） |
| GET | `/tours/<int:line_id>/register` | public | 报名表单页（选中 departure 后可 POST） |
| POST | `/tours/<int:line_id>/register` | public | 提交报名（创建 tour.plan.reg） |
| GET | `/tours/register/success/<int:reg_id>` | public | 报名成功页 |
| GET | `/my/registrations` | user(portal) | （可选）我的报名列表 |

### 4.2 控制器骨架（设计参考）

```python
# controllers/main.py
from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError


class TourWebsite(http.Controller):

    # ---------- 线路列表 ----------
    @http.route('/tours', type='http', auth='public', website=True, sitemap=True)
    def tour_list(self, **kw):
        # sudo() 读取：tour.line 仅对内部用户授权，public 需提权读
        TourLine = request.env['tour.line'].sudo()
        domain = [('active', '=', True), ('audit_state', '=', 'approved')]
        # 可选筛选：line_type_id / from_city / day_num
        lines = TourLine.search(domain, order='sequence, name')
        return request.render('tour_website.tour_list', {
            'lines': lines,
        })

    # ---------- 线路详情 ----------
    @http.route('/tours/<int:line_id>', type='http', auth='public', website=True, sitemap=True)
    def tour_detail(self, line_id, **kw):
        line = request.env['tour.line'].sudo().browse(line_id).exists()
        if not line or not line.active or line.audit_state != 'approved':
            return request.not_found()
        departures = request.env['tour.departure'].sudo().search([
            ('line_id', '=', line.id),
            ('state', '=', 'published'),
            ('start_date', '>=', fields.Date.today()),
        ], order='start_date asc')
        # 取出发日期 >= today 且 remain_seats > 0 的班期
        return request.render('tour_website.tour_detail', {
            'line': line,
            'departures': departures,
        })

    # ---------- 报名提交 ----------
    @http.route('/tours/<int:line_id>/register', type='http', auth='public',
                website=True, methods=['POST'], csrf=True)
    def tour_register(self, line_id, **post):
        line = request.env['tour.line'].sudo().browse(line_id).exists()
        departure = request.env['tour.departure'].sudo().browse(
            int(post.get('departure_id', 0))).exists()
        # 服务端校验 + 创建，见 tour_plan_reg.py
        reg = request.env['tour.plan.reg'].sudo().create_online_reg(line, departure, post)
        return request.redirect('/tours/register/success/%s' % reg.id)
```

### 4.3 报名创建方法（放在模型层，Controller 只做薄转发）

```python
# models/tour_plan_reg.py
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TourPlanReg(models.Model):
    _inherit = 'tour.plan.reg'

    def create_online_reg(self, line, departure, vals):
        """在线报名入口：校验 + 定位/创建承载团队 + 创建报名 + 回写余位。
        全程 sudo() 执行（public 无 write/create 权限），但校验在方法内完成。
        """
        self = self.sudo()
        # 1) 校验
        if not line or not departure or departure.line_id.id != line.id:
            raise ValidationError(_('线路与班期不匹配'))
        if departure.state != 'published' or departure.start_date < fields.Date.today():
            raise ValidationError(_('该班期不可报名'))
        if departure.remain_seats <= 0:
            raise ValidationError(_('该班期已满'))

        adult = int(vals.get('adult_num') or 0)
        child = int(vals.get('child_num') or 0)
        total = adult + child
        if total <= 0:
            raise ValidationError(_('请填写报名人数'))
        if total > departure.remain_seats:
            raise ValidationError(_('余位不足（剩余 %s 位）') % departure.remain_seats)
        for f in ('supplier_name', 'supplier_user_mobile'):
            if not (vals.get(f) or '').strip():
                raise ValidationError(_('姓名与手机为必填'))

        # 2) 定位/创建承载团队 tour.plan（团期计划 DSK）
        plan = self._get_or_create_plan(line, departure)

        # 3) 生成报名单号（唯一）
        reg_code = self.env['ir.sequence'].next_by_code('tour.plan.reg.online') \
            or 'ON%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')

        # 4) 创建报名
        reg = self.create({
            'reg_code': reg_code,
            'plan_id': plan.id,
            'first_plan_id': plan.id,
            'biz_mode': '12',          # 团期计划 DSK（或 14 散客并团，视并团策略）
            'plan_type': '2',          # 散客/散拼
            'from_type': '1',          # 内部（可加 B2C 标记）
            'begin_date': departure.start_date,
            'end_date': departure.end_date,
            'adult_num': adult,
            'child_num': child,
            'guest_count': total,
            'supplier_name': vals.get('supplier_name'),
            'supplier_user': vals.get('supplier_user', ''),
            'supplier_user_mobile': vals.get('supplier_user_mobile'),
            # 报价 = 成人价*成人 + 儿童价*儿童（线下付款，仅记录应收）
            'in_com_quo_sum': departure.price_adult * adult
                            + (departure.price_child or 0) * child,
            'remark': vals.get('remark', '') + ' [线上报名]',
        })

        # 5) 回写余位
        departure.booked_seats += total
        return reg

    def _get_or_create_plan(self, line, departure):
        """同线路同班期复用承载团队，否则新建团期计划。"""
        existing = self.env['tour.plan'].search([
            ('line_id', '=', line.id),
            ('begin_date', '=', departure.start_date),
            ('biz_mode', '=', '12'),
        ], limit=1)
        if existing:
            return existing
        plan_code = self.env['ir.sequence'].next_by_code('tour.plan.online') \
            or 'PL%s' % fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        return self.env['tour.plan'].create({
            'plan_code': plan_code,
            'plan_name': '%s-%s' % (line.name, departure.start_date),
            'line_id': line.id,
            'biz_mode': '12',
            'plan_type': '2',
            'from_type': '1',
            'begin_date': departure.start_date,
            'end_date': departure.end_date,
            'channel_name': 'B2C线上',
            'state': 'draft',          # 线下付款后由计调确认流转
        })
```

---

## 五、QWeb 视图设计

### 5.1 线路列表页 `tour_list`

- 继承 `website.layout`，复用标准站点导航/页脚。
- 卡片网格展示：线路名、天数、出发地/目的地、成人价、分类、特色标签（`is_abroad`/`is_special`）。
- 关键词搜索 + 分类/出发城市筛选（server-side search 或前端过滤，本期用 server-side）。

```xml
<template id="tour_list" name="线路列表">
  <t t-call="website.layout">
    <div id="wrap" class="oe_structure">
      <t t-foreach="lines" t-as="line">
        <a t-attf-href="/tours/#{line.id}" class="card">
          <h3 t-esc="line.name"/>
          <span t-esc="line.day_num"/> 天
          <span t-esc="line.send_place"/> → <span t-esc="line.end_place"/>
          <b t-esc="line.adult_price"/> 起
        </a>
      </t>
    </div>
  </t>
</template>
```

### 5.2 线路详情页 `tour_detail`

- 线路主图/标题/价格/天数/费用包含（`fee_include`）/费用不含（`fee_exclude`）。
- 行程安排（`srv_text`）、线路特色（`feature_rich`）以富文本渲染。
- 行程明细 `tour.line.detail` 按 `day_no` 循环展示（第 N 天标题/城市/餐/住宿/交通/内容）。
- 班期列表：可报名班期（`departures`）显示出发日期、余位、价格，点击进入报名。

### 5.3 报名表单页 + 成功页

- 表单字段：班期（hidden `departure_id`）、姓名、手机、成人数、儿童数、备注。
- 金额/余位为只读展示（由 departure 派生，不可被客户端篡改，服务端重算）。
- 提交后重定向成功页，展示 `reg_code` 报名单号 + 线下付款提示。

```xml
<template id="tour_register" name="在线报名">
  <t t-call="website.layout">
    <form method="post" t-attf-action="/tours/#{line.id}/register" class="s_website_form">
      <input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>
      <input type="hidden" name="departure_id" t-att-value="departure.id"/>
      <input type="text" name="supplier_name" required="1" placeholder="姓名"/>
      <input type="tel" name="supplier_user_mobile" required="1" placeholder="手机号"/>
      <input type="number" name="adult_num" min="0" placeholder="成人数"/>
      <input type="number" name="child_num" min="0" placeholder="儿童数"/>
      <textarea name="remark" placeholder="备注"/>
      <button type="submit">提交报名</button>
    </form>
  </t>
</template>
```

> 注：Odoo 19 中 csrf 令牌可用 `request.csrf_token()` 渲染到 hidden 字段；JSON 路由则由框架默认 `csrf=True` 处理。实际落地时以当前 `website` 版本的内置 form 片段（`website_form`）为准验证令牌注入方式。

### 5.4 SEO / sitemap

- 列表、详情路由标记 `sitemap=True`，实现 `sitemap_*` 方法或依赖 `active/audit_state` 过滤。
- 详情页 `website_meta_title/description` 由线路名/特色派生，提升搜索引擎收录。

---

## 六、数据模型与访问权限变更

### 6.1 新增/变更字段（最小集）

| 模型 | 字段 | 类型 | 说明 |
|------|------|------|------|
| `tour.line` | `website_published` | Boolean | 是否前台展示（默认 False，审核通过才可上架），可选替代用 `audit_state='approved'` |
| `tour.departure` | `online_bookable` | Boolean | 是否开放线上报名（可选，默认 published 即可报名） |
| `tour.plan.reg` | `source` / `channel_name` | Char | 标记「B2C线上」来源，便于统计与风控 |
| `ir.sequence` | `tour.plan.reg.online` / `tour.plan.online` | — | 报名单号 / 团号序列（data XML 预置） |

> 最小化原则：能用 `active + audit_state` 就不加新字段。`website_published` 仅当需要「审核通过但暂不上架」的独立开关时才加。

### 6.2 访问权限（关键）

现有 `ir.model.access.csv` 仅授权内部用户（`base.group_user`），**public / portal 用户无任何 tour 模型权限**。方案：

| 模型 | public（未登录） | portal（登录） | 做法 |
|------|------------------|----------------|------|
| `tour.line` / `tour.departure` / `tour.line.detail` | 只读 | 只读 | Controller 内 `sudo()` 读取，**不**给 public 直接授权 |
| `tour.plan.reg` | 创建（经 controller 方法） | 创建 + 查看自己的 | `create_online_reg()` 用 `sudo()` 执行，校验在方法内；不给 public 直接 write/create 授权 |
| `tour.plan` | 无 | 无 | 仅内部，前台不暴露 |

**安全要点**：
- 不让 public 直接持有 ORM create/write 权限（防止绕过校验批量注入脏数据）。
- 所有写操作收敛到 `create_online_reg()` 单一入口，内部做完整校验。
- 读操作 `sudo()` 前过滤 `active`、`audit_state`、`state`、`remain_seats`，防止未审核/已结束线路外泄。

### 6.3 敏感字段处理

- 手机号 `supplier_user_mobile` 属 PII（代码已标 🟡 敏感字段）。
- `tour_base` 提供 `tour.encrypted.field.mixin` + AES-256-GCM 落盘加密（见 `tour_base/models/encrypted_field_mixin.py` / `field_crypto.py`）。
- 线上报名收集的手机号应沿用该加密 mixin 落盘；表单展示、后台列表按「敏感数据完整值查看组」脱敏。

---

## 七、关键技术点（Odoo 19 website/portal API）

### 7.1 public route

```python
@http.route('/tours', type='http', auth='public', website=True, sitemap=True)
def ...(self, **kw):
    ...
```
- `auth='public'`：未登录可访问。
- `website=True`：自动套用当前网站（多网站场景按 website 上下文渲染）。
- `type='http'` 返回 `request.render()` 的 HTML；`type='json'` 用于 ajax（返回 JSON，默认 `csrf=True`）。

### 7.2 CSRF（Odoo 19）

- POST 的 `type='http'` 路由默认启用 CSRF 校验（`csrf=True` 默认），表单需携带令牌。
- 令牌注入：QWeb 中 `request.csrf_token()` 或标准 form 片段；JSON 路由由框架处理。
- 切勿为图省事设 `csrf=False`（public 可被跨站伪造报名）。

### 7.3 sudo() 边界

- 读：`request.env['tour.line'].sudo().search(domain)`。
- 写：`request.env['tour.plan.reg'].sudo().create_online_reg(...)`，**校验在方法内**，不信任任何客户端字段。
- 金额/日期/余位一律服务端重算，前端只做展示。

### 7.4 单号生成

- `reg_code` / `plan_code` 均为 `required + unique`（代码中有唯一约束），线上创建必须生成。
- 用 `ir.sequence`（data XML 预置 `tour.plan.reg.online`、`tour.plan.online`），避免并发下手工拼接撞号。

### 7.5 并发余位控制

- `booked_seats += total` 在事务内；高并发下建议对 `tour.departure` 行加锁（`FOR UPDATE`）或先 `search([('remain_seats','>=',total)])` 再写，必要时用 `@api.constrains` 兜底（`booked_seats <= seats`）。
- 最小闭环并发压力低，事务内校验即可，标注为后续优化点。

### 7.6 mail.thread 追踪

- `tour.plan.reg` 继承 `mail.thread`，create 会生成 tracking 消息。public 场景下消息由系统用户（SUPERUSER）发出，需注意 `create_uid` 语义；必要时在方法内显式指定 `op_user_id`（操作员）记录真实归属。

---

## 八、无登录报名 vs portal 登录（技术选型）

| 维度 | 无登录报名（✅ 本期） | portal 登录 |
|------|----------------------|-------------|
| 转化率 | 高（无注册流失） | 低（登录是流失点） |
| 实现复杂度 | 低（`auth='public'` + controller 校验） | 中（`auth='user'` + portal_layout + 绑定 res.partner） |
| 查单能力 | 需另建「凭手机号查单」或不做 | 天然「我的报名」 |
| 客户沉淀 | 弱（仅手机号） | 强（关联 res.partner） |
| 风险 | 需防刷单/脏数据（服务端校验兜底） | 有账号体系约束 |

**决策**：最小闭环采用**无登录报名**，理由：
1. 散客 B2C 转化率优先，登录是首要流失点。
2. 报名仅需「姓名 + 手机 + 人数」，无需账户体系。
3. 后续可在不破坏现有数据流的前提下，增量增加「portal 登录 + 我的报名」（`/my/registrations`，`auth='user'`），此时 `supplier_id` 关联登录用户的 `res.partner` 即可平滑演进。

**演进预留**：
- `depends` 已含 `portal`，登录查单能力可随时加，不影响本期。
- 报名记录保留 `supplier_id`（Many2one res.partner），登录后回填。

---

## 九、安全与风控

| 风险 | 对策 |
|------|------|
| 刷单/垃圾报名 | 服务端必填校验 + 手机号格式校验；可选 IP 限流（Nginx `/tours/register` 限流）；验证码（`website_cf_turnstile` 已可用的 Cloudflare Turnstile） |
| 越权访问未审核线路 | 读取统一过滤 `active=True` + `audit_state='approved'` + `state` 有效 |
| 篡改金额/班期 | 金额、日期、班期全部服务端重算，前端只读 |
| PII 泄露 | 手机号加密落盘 + 后台脱敏展示 |
| 余位超卖 | 事务内校验 `remain_seats`，`@api.constrains` 兜底 `booked_seats <= seats` |
| CSRF | POST 路由保持 `csrf=True` 默认，表单注入令牌 |

---

## 十、实施步骤与工作量估算

| # | 任务 | 内容 | 人天 |
|---|------|------|------|
| 1 | 模块骨架 | manifest / __init__ / 目录结构 | 0.5 |
| 2 | 访问权限 + 序列 | ir.model.access（仅内部模型授权不变）、ir.sequence 预置 | 0.5 |
| 3 | 展示 controller + QWeb | 列表页、详情页、行程明细渲染、班期列表 | 3 |
| 4 | 报名 controller + 模型方法 | `create_online_reg`、`_get_or_create_plan`、校验、余位回写 | 3 |
| 5 | 成功页 + 风控 | 成功页、手机号校验、限流/验证码 | 1.5 |
| 6 | 单元测试 | 报名创建、余位超卖、越权读取、单号唯一 | 2 |
| 7 | 联调 + SEO | sitemap、meta、线上验证 | 1 |
| | **合计** | | **11.5 人天** |

---

## 附：环境实测结论（2026-09-13）

- Odoo 版本：`19.0.post20260817`（tms-odoo 容器）。
- 标准模块已安装：`website`、`portal`、`website_sale`、`website_crm`（`website_blog/event/forum` 未装）。
- 自定义模块已安装：`tour_base`、`tour_product`、`tour_order`、`tour_resource`、`tour_operation`、`tour_shopping`、`tour_accounting`、`tour_budget`、`tour_report`。
- 因此 `tour_website` 直接依赖 `website`/`portal` 均满足，无需额外安装标准模块。
