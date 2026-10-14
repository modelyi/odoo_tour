# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaDispatchItem(models.Model):
    """计调资源条目：一单团一资源一行；确认后生成供应商账单草稿。

    NFR-2：move_id 已有值不得重复生成；条目确认后金额锁定，改价须取消重开。
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

    departure_id = fields.Many2one(
        'ta.departure', string='发团计划', required=True, ondelete='cascade',
        index=True, tracking=True)
    route_id = fields.Many2one(related='departure_id.route_id', store=True)
    kind = fields.Selection(KIND, required=True, tracking=True)
    supplier_id = fields.Many2one('res.partner', string='供应商', required=True, tracking=True)
    name = fields.Char(string='项目说明', required=True)
    date_start = fields.Date(related='departure_id.date_start', string='开始日期')
    qty = fields.Float(string='数量', default=1.0, required=True)
    unit_price = fields.Float(string='单价', required=True)
    amount = fields.Float(compute='_compute_amount', store=True)
    note = fields.Char()
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已确认'),
        ('cancel', '已取消'),
    ], default='draft', required=True, tracking=True, copy=False)
    move_id = fields.Many2one('account.move', string='供应商账单', readonly=True, copy=False)

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

    def action_confirm(self):
        for item in self:
            if item.state != 'draft':
                raise UserError("只有草稿条目可以确认。")
            if item.departure_id.state not in ('open', 'confirmed', 'departed', 'settled'):
                raise UserError("发团计划当前状态不允许确认计调单。")
            item.move_id = item._create_supplier_bill()
            item.state = 'confirmed'
        return True

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
        if self.departure_id.biz_mode_id.code == '41':
            expense = self._ta_get_account(
                '224101', '其他应付款-代收代付', 'liability_payable')
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
                # O20 坑：负债类科目（224101）行会被自动归类 display_type='payment_term'，
                # 不满足 invoice_line_ids 的 comodel domain；显式钉回 'product' 行。
                'display_type': 'product',
                # O20 校验：Payable 科目分录必须带到期日。
                'date_maturity': fields.Date.context_today(self),
                'quantity': self.qty,
                'price_unit': self.unit_price,
            })],
        })
        return move


class TaDepartureDispatch(models.Model):
    _inherit = 'ta.departure'

    dispatch_item_ids = fields.One2many('ta.dispatch.item', 'departure_id', string='计调单')
    dispatch_cost_total = fields.Float(compute='_compute_dispatch_cost', store=True)

    @api.depends('dispatch_item_ids.state', 'dispatch_item_ids.amount')
    def _compute_dispatch_cost(self):
        for dep in self:
            dep.dispatch_cost_total = sum(
                dep.dispatch_item_ids.filtered(lambda i: i.state == 'confirmed').mapped('amount'))
