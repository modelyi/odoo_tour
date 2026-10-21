# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaDispatchItem(models.Model):
    """计调资源条目：一单团一资源一行；确认后生成供应商账单草稿。

    NFR-2：move_id 已有值不得重复生成；条目确认后金额锁定，改价须取消重开。

    批7（BS-03 补齐）：
    - 类型明细字段（酒店房型 / 餐厅餐次桌数 / 门票票种 / 车辆接送），
      明细改动自动回填 qty / unit_price（沿用批6 P1-8 的 editable compute 模式）；
    - 状态机扩展 completed（发团结算完成时联动）；
    - 导游/领队/车辆跨团日期冲突检测（US-03-07，ICP ta_dispatch.conflict_check 默认开）；
    - 酒店/景区预订二次确认 confirm_state（US-03-08，营运中心）。
    """
    _name = 'ta.dispatch.item'
    _description = '计调单（资源安排）'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'departure_id desc, kind, id'

    # 语义参考 tour_base/constants.py::SUP_TYPE，按新产品口径增导游/领队
    KIND = [
        ('ditch', '地接社'),
        ('hotel', '酒店'),
        ('meal', '餐厅'),
        ('vehicle', '车队'),
        ('ticket', '票务'),
        ('scenic', '景区'),
        ('guide', '导游'),
        ('leader', '领队'),
        ('other', '其他'),
    ]

    MEAL_TYPE = [
        ('breakfast', '早餐'),
        ('lunch', '午餐'),
        ('dinner', '晚餐'),
    ]

    departure_id = fields.Many2one(
        'ta.departure', string='发团计划', required=True, ondelete='cascade',
        index=True, tracking=True)
    route_id = fields.Many2one(related='departure_id.route_id', store=True)
    kind = fields.Selection(KIND, required=True, tracking=True)
    supplier_id = fields.Many2one('res.partner', string='供应商', required=True, tracking=True)
    name = fields.Char(string='项目说明', required=True)
    # 批7：改存储列，供冲突检测与 SQL 视图按条目日期检索（原 related 非存储）。
    date_start = fields.Date(related='departure_id.date_start', string='开始日期', store=True)
    date_end = fields.Date(
        compute='_compute_date_end', store=True, readonly=False, copy=False,
        string='结束日期', tracking=True,
        help='酒店为退房日，多日资源与开始日期不同；单日资源与开始日期相同。')
    guest_count = fields.Integer(
        compute='_compute_guest_count', store=True, readonly=False, string='人数',
        help='默认取发团计划已占位人数，可改；酒店语义为总间数。')
    qty = fields.Float(
        string='数量', default=1.0, required=True,
        compute='_compute_qty', store=True, readonly=False)
    unit_price = fields.Float(
        string='单价', default=0.0, required=True,
        compute='_compute_unit_price', store=True, readonly=False)
    amount = fields.Float(compute='_compute_amount', store=True)
    note = fields.Char()
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已确认'),
        ('completed', '已完成'),
        ('cancel', '已取消'),
    ], default='draft', required=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='供应商账单', readonly=True, copy=False)

    # ---- 批7：类型明细字段（BS-03 §3.1；按 kind 条件可见，全部可空）----
    # 酒店
    night_num = fields.Integer(
        compute='_compute_night_num', store=True, string='晚数',
        help='= 结束日期 − 开始日期；单日为 0，按 1 晚计价。')
    room_price = fields.Float(string='每晚房价（每间）')
    room_single = fields.Integer(string='单间数')
    room_standard = fields.Integer(string='标准间数')
    room_triangle = fields.Integer(string='三人间数')
    room_accompany = fields.Integer(string='陪同房数')
    room_additional = fields.Integer(string='加床房数')
    # 餐厅
    meal_type = fields.Selection(MEAL_TYPE, string='餐次')
    table_count = fields.Integer(string='桌数')
    price_per_table = fields.Float(string='每桌餐标')
    # 景区（票务同用，票种人数）
    ticket_adult = fields.Integer(string='成人票数')
    ticket_child = fields.Integer(string='儿童票数')
    ticket_old = fields.Integer(string='老人票数')
    ticket_student = fields.Integer(string='学生票数')
    # 车辆
    seat_num = fields.Integer(string='所需座位数',
                             help='校验用，建议 ≥ 人数 + 司陪。')
    pick_time = fields.Datetime(string='接站时间')
    pick_place = fields.Char(string='接站地点')
    drop_time = fields.Datetime(string='送站时间')
    drop_place = fields.Char(string='送站地点')

    # ---- 批7：营运中心二次确认（US-03-08，仅酒店/景区）----
    # 不设 required（ORM 层有 default）：历史迁移脚本以 raw SQL 直写本表
    # （见 scripts/migrate_tms19_to_ta.py），NOT NULL 会破坏其重跑幂等。
    confirm_state = fields.Selection([
        ('unconfirmed', '未确认'),
        ('confirmed', '预订已确认'),
        ('rejected', '预订已取消'),
    ], default='unconfirmed', copy=False,
        string='预订确认状态', tracking=True)

    # ---- 批3-2 付款闭环透出（付款动作本身在会计侧账单完成，这里只透出状态） ----
    bill_state = fields.Selection([
        ('none', '无账单'),
        ('draft', '账单草稿'),
        ('posted', '账单已过账'),
        ('cancel', '账单已作废'),
    ], string='账单状态', compute='_compute_bill_state', store=False, readonly=True)
    # O20 核实（account/models/account_move.py::_compute_amount）：in_invoice 的
    # amount_total / amount_residual 均为 store=True 有列、正数口径（direction_sign=1），
    # 已付 = amount_total - amount_residual；draft 账单 residual=total → 已付 0。
    paid_amount = fields.Float(
        string='已付款额', compute='_compute_paid_amount', store=False, readonly=True,
        help='挂账供应商账单的已付款金额（amount_total - amount_residual，仅已过账单）。')
    # 设计说明（批3-3 依赖）：**存储字段** store=True + readonly=False。
    # - 有新账单：compute 取账单核销付款（account.payment, state paid/reconciled）的最大 date；
    #   账单存在但未付时置 False；
    # - 无账单（历史迁移条目）：compute 不赋值 → 保留迁移脚本 raw SQL
    #   `UPDATE/INSERT ta_dispatch_item.paid_date` 的直写值（列名 ta_dispatch_item.paid_date，
    #   date 类型，可空；语义=该条目付款完成日，无账单时"有值即视为已付该条目全额"，
    #   口径由 ta.supplier.payable.paid_total 消费）。
    paid_date = fields.Date(
        string='付款日期', compute='_compute_paid_date', store=True, readonly=False, copy=False,
        help='条目付款完成日。有账单时取账单核销付款的最大日期；'
             '无账单的历史条目可由迁移脚本直写，compute 不覆盖。')

    _amount_check = models.Constraint(
        "check(qty > 0 and unit_price >= 0)",
        '数量必须为正，单价不得为负（NFR-1：金额方向不取绝对值）。')

    # ---- 批7：默认值回填（editable compute，语义同 paid_date：不赋值即保留现值）----
    @api.depends('departure_id')
    def _compute_date_end(self):
        for item in self:
            if not item.date_end:
                dep = item.departure_id
                item.date_end = dep.date_end or dep.date_start

    @api.depends('departure_id')
    def _compute_guest_count(self):
        for item in self:
            if not item.guest_count:
                item.guest_count = item.departure_id.seats_used

    @api.depends('date_start', 'date_end')
    def _compute_night_num(self):
        for item in self:
            if item.date_start and item.date_end and item.date_end >= item.date_start:
                item.night_num = (item.date_end - item.date_start).days
            else:
                item.night_num = 0

    def _ta_detail_qty(self):
        """按类型明细计算数量；无明细返回 0（不动现值）。"""
        self.ensure_one()
        if self.kind == 'hotel':
            return (self.room_single + self.room_standard + self.room_triangle
                    + self.room_accompany + self.room_additional)
        if self.kind == 'meal':
            return self.table_count
        if self.kind in ('scenic', 'ticket'):
            return (self.ticket_adult + self.ticket_child
                    + self.ticket_old + self.ticket_student)
        return 0

    def _ta_detail_unit_price(self):
        """按类型明细计算单价；无明细返回 0（不动现值）。"""
        self.ensure_one()
        if self.kind == 'hotel' and self.room_price:
            return self.room_price * max(self.night_num, 1)
        if self.kind == 'meal' and self.price_per_table:
            return self.price_per_table
        return 0

    @api.depends('kind', 'room_single', 'room_standard', 'room_triangle',
                 'room_accompany', 'room_additional', 'table_count',
                 'ticket_adult', 'ticket_child', 'ticket_old', 'ticket_student')
    def _compute_qty(self):
        for item in self:
            detail_qty = item._ta_detail_qty()
            if detail_qty:
                item.qty = detail_qty
            elif not item.qty:
                item.qty = 1.0

    @api.depends('kind', 'room_price', 'price_per_table', 'night_num')
    def _compute_unit_price(self):
        for item in self:
            detail_price = item._ta_detail_unit_price()
            if detail_price:
                item.unit_price = detail_price

    @api.depends('qty', 'unit_price')
    def _compute_amount(self):
        for item in self:
            item.amount = item.qty * item.unit_price

    @api.depends('move_id', 'move_id.state')
    def _compute_bill_state(self):
        for item in self:
            item.bill_state = item.move_id.state if item.move_id else 'none'

    @api.depends('move_id', 'move_id.state', 'move_id.amount_total',
                 'move_id.amount_residual')
    def _compute_paid_amount(self):
        for item in self:
            move = item.move_id
            # NFR-1：直取差值，不做 abs() 方向修正（in_invoice 两值均正数口径）
            item.paid_amount = (
                move.amount_total - move.amount_residual
                if move and move.state == 'posted' else 0.0)

    @api.depends('move_id', 'move_id.payment_state', 'move_id.amount_residual')
    def _compute_paid_date(self):
        for item in self:
            if not item.move_id:
                continue  # 无账单：不触碰现值 → 保留迁移/手填直写的历史付款日
            move = item.move_id
            dates = move.reconciled_payment_ids.filtered(
                lambda p: p.state in ('paid', 'reconciled')).mapped('date')
            item.paid_date = max(dates) if dates else False

    # ---- 批7：资源冲突检测（BS-03 US-03-07）----
    def _ta_check_resource_conflict(self):
        """导游/领队/车辆三类"人车硬资源"：同供应商在日期重叠的另一个团上
        已有非取消条目 → 拦截确认。历史迁移条目 kind 均为 other，不受影响。

        ICP `ta_dispatch.conflict_check` 默认开；关掉即放行（口径裁定用）。
        date_end 为空按单日（=date_start）参与重叠判断。
        """
        self.ensure_one()
        if self.kind not in ('guide', 'leader', 'vehicle'):
            return
        if not self.env['ir.config_parameter'].sudo().get_bool(
                'ta_dispatch.conflict_check', True):
            return
        start = self.date_start
        if not start:
            return
        end = self.date_end or start
        base = [
            ('id', '!=', self.id),
            ('kind', '=', self.kind),
            ('supplier_id', '=', self.supplier_id.id),
            ('state', '!=', 'cancel'),
            ('departure_id', '!=', self.departure_id.id),
            ('company_id', '=', self.company_id.id),
        ]
        # ① 对方条目带日期区间：区间重叠
        span = self.search(base + [
            ('date_start', '<=', end), ('date_end', '>=', start)])
        # ② 对方条目无 date_end（历史单日）：落在本条目区间内
        single = self.search(base + [
            ('date_end', '=', False),
            ('date_start', '>=', start), ('date_start', '<=', end)])
        others = span | single
        if others:
            dep = others[0].departure_id
            raise UserError(
                f"资源冲突（US-03-07）：{self.supplier_id.display_name} 已被发团计划"
                f"「{dep.code or dep.display_name}」（{others[0].date_start}~"
                f"{others[0].date_end or others[0].date_start}）占用，"
                f"同一供应商不能在重叠日期派给两个团。"
                f"冲突条目：{', '.join(others.mapped('display_name'))}。")

    def action_confirm(self):
        for item in self:
            if item.state != 'draft':
                raise UserError("只有草稿条目可以确认。")
            if item.departure_id.state not in ('open', 'confirmed', 'departed', 'settled'):
                raise UserError("发团计划当前状态不允许确认计调单。")
            item._ta_check_resource_conflict()
            item.move_id = item._create_supplier_bill()
            item.state = 'confirmed'

    def action_complete(self):
        """批7：已完成（资源使用完毕）。发团结算完成时由 settle 钩子自动批量置位。"""
        for item in self:
            if item.state != 'confirmed':
                raise UserError("只有已确认的计调单可以标记完成。")
            item.state = 'completed'

    # ---- 批7：营运中心二次确认（US-03-08；仅酒店/景区开放按钮）----
    def action_confirm_booking(self):
        for item in self:
            if item.kind not in ('hotel', 'scenic'):
                raise UserError("只有酒店/景区条目需要营运中心二次确认。")
            item.confirm_state = 'confirmed'

    def action_reject_booking(self):
        for item in self:
            if item.kind not in ('hotel', 'scenic'):
                raise UserError("只有酒店/景区条目支持预订取消。")
            item.confirm_state = 'rejected'

    def action_cancel(self):
        for item in self:
            if item.state == 'cancel':
                raise UserError("条目已取消。")
            if item.move_id:
                if item.move_id.state != 'draft':
                    raise UserError("供应商账单已过账，请先在会计侧处理，不能直接取消计调单。")
                item.move_id.unlink()
            item.state = 'cancel'

    def action_reset_draft(self):
        for item in self:
            if item.state != 'cancel':
                raise UserError("只有已取消条目可以恢复为草稿。")
            if item.move_id:
                raise UserError("该条目仍挂着账单，无法恢复。")
            item.state = 'draft'

    def _create_supplier_bill(self):
        self.ensure_one()
        partner = self.supplier_id
        # 批6 P0-6：成本科目按业务模式分流（BS-14）：41 代订 → 2241.01 代收代付
        # （成本经代收代付转出，不进损益）；其余模式 → 6401 主营业务成本。
        # O20 约束：采购单据里 liability_payable 行必须是 payment_term 行，而
        # invoice_line_ids 只接受 product 行 → 224101 用 liability_current。
        if self.departure_id.biz_mode_id.code == '41':
            expense = self._ta_get_account(
                '224101', '其他应付款-代收代付', 'liability_current')
        else:
            expense = self._ta_get_account('6401', '主营业务成本', 'expense')
        journal = self.env['account.journal'].search(
            [('type', '=', 'purchase'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError("当前公司没有采购日记账，无法生成供应商账单。")
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'journal_id': journal.id,
            'partner_id': partner.id,
            # 批6 P1-7：账单日期取操作当日，不再取发团日（避免未来日期账单）
            'date': fields.Date.context_today(self),
            # O20 硬校验（account_move._post）：in_invoice 过账必须填 invoice_date，
            # 否则"Bill/Refund date is required"拦截，付款闭环无法走通 → 建单即带上。
            'invoice_date': fields.Date.context_today(self),
            'ref': f"计调单 {self.departure_id.code or ''} {self.name}",
            'invoice_line_ids': [(0, 0, {
                'name': self.name,
                'account_id': expense.id,
                # 显式钉 product 行，避免 O20 自动归类干扰 invoice_line_ids 域。
                'display_type': 'product',
                'quantity': self.qty,
                'price_unit': self.unit_price,
            })],
        })
        return move


class TaDepartureDispatch(models.Model):
    _inherit = 'ta.departure'

    dispatch_item_ids = fields.One2many('ta.dispatch.item', 'departure_id', string='计调单')
    dispatch_cost_total = fields.Float(compute='_compute_dispatch_cost', store=True)

    # ---- 批7：计调进度看板（BS-03 US-03-01）----
    dispatch_active_count = fields.Integer(
        compute='_compute_dispatch_progress', store=True, string='计调条目数',
        help='未取消的计调条目总数。')
    dispatch_done_count = fields.Integer(
        compute='_compute_dispatch_progress', store=True, string='已确认/完成数',
        help='已确认 + 已完成的条目数。')
    dispatch_completion_rate = fields.Float(
        compute='_compute_dispatch_progress', store=True, string='计调完成度 %',
        help='（已确认 + 已完成）/ 未取消条目 × 100。')
    dispatch_kind_summary = fields.Char(
        compute='_compute_dispatch_progress', store=True, string='资源安排摘要',
        help='按类型汇总："酒店2/2 餐0/1 …"，只列已有条目的类型。')

    @api.depends('dispatch_item_ids.state', 'dispatch_item_ids.amount', 'dispatch_item_ids.kind')
    def _compute_dispatch_cost(self):
        for dep in self:
            dep.dispatch_cost_total = sum(
                dep.dispatch_item_ids.filtered(
                    lambda i: i.state in ('confirmed', 'completed')).mapped('amount'))

    @api.depends('dispatch_item_ids.state', 'dispatch_item_ids.kind')
    def _compute_dispatch_progress(self):
        kind_label = dict(self.env['ta.dispatch.item'].fields_get(
            allfields=['kind'])['kind']['selection'])
        for dep in self:
            active = dep.dispatch_item_ids.filtered(lambda i: i.state != 'cancel')
            done = active.filtered(lambda i: i.state in ('confirmed', 'completed'))
            dep.dispatch_active_count = len(active)
            dep.dispatch_done_count = len(done)
            dep.dispatch_completion_rate = (
                len(done) * 100.0 / len(active)) if active else 0.0
            parts = []
            for kind, label in kind_label.items():
                rows = active.filtered(lambda i: i.kind == kind)
                if rows:
                    ok = len(rows.filtered(lambda i: i.state in ('confirmed', 'completed')))
                    parts.append(f"{label}{ok}/{len(rows)}")
            dep.dispatch_kind_summary = '  '.join(parts)

    def action_settle(self):
        """批7：结算完成时把已确认计调条目自动置为已完成（资源已用尽、账单已挂）。"""
        res = super().action_settle()
        for dep in self:
            dep.dispatch_item_ids.filtered(
                lambda i: i.state == 'confirmed').write({'state': 'completed'})
        return res
