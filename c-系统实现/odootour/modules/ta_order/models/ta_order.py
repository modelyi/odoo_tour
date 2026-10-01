# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class TaOrder(models.Model):
    _name = 'ta.order'
    _description = '团队/散客订单'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'date_confirm desc, id desc'

    name = fields.Char(string='订单号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.order') or '/')
    kind = fields.Selection([
        ('team', '团队'),
        ('fit', '散客'),
    ], string='订单类型', default='team', required=True)
    partner_id = fields.Many2one('res.partner', string='客户',
                                 help='团队输单时的组团社/单位客户；散客可留空。')
    departure_id = fields.Many2one(
        'ta.departure', string='发团计划', required=True, index=True,
        domain="[('state', 'in', ('open', 'confirmed'))]", tracking=True)
    route_id = fields.Many2one(related='departure_id.route_id', store=True, readonly=False)
    biz_mode_id = fields.Many2one('ta.biz.mode', string='业务模式',
                                  domain="[('is_alias', '=', False)]")
    date_confirm = fields.Date(default=fields.Date.context_today)
    line_ids = fields.One2many('ta.order.line', 'order_id', string='报名名单')
    heads = fields.Integer(string='人数', compute='_compute_totals', store=True)
    amount_total = fields.Float(string='应收总额', compute='_compute_totals', store=True,
                                digits=(12, 2))
    amount_paid = fields.Float(string='已认领到账', readonly=True, copy=False,
                               digits=(12, 2), tracking=True)
    amount_open = fields.Float(compute='_compute_amount_open', store=True, digits=(12, 2))
    plan_ids = fields.One2many('ta.receivable.plan', 'order_id', string='收款期次')
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已确认'),
        ('tripping', '行程中'),
        ('settled', '已结算'),
        ('cancel', '取消'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    seats_released = fields.Boolean(copy=False, default=False)
    note = fields.Char()

    _heads_check = models.Constraint(
        'check(state = \'draft\' or heads > 0)',
        '确认后的订单必须至少有一名报名人。')

    @api.depends('line_ids', 'line_ids.amount')
    def _compute_totals(self):
        for order in self:
            order.heads = len(order.line_ids)
            order.amount_total = sum(order.line_ids.mapped('amount'))

    @api.depends('amount_total', 'amount_paid')
    def _compute_amount_open(self):
        for order in self:
            order.amount_open = order.amount_total - order.amount_paid

    def _ta_apply_paid(self, delta):
        """仅供 ta_finance 审核/反审核调用；正向幂等由认领单状态机保证。"""
        for order in self:
            new_paid = order.amount_paid + delta
            if new_paid < -0.01 or new_paid > order.amount_total + 0.01:
                raise UserError(
                    f"订单 {order.name} 到账核销越界（已付 {order.amount_paid:.2f}，"
                    f"应收 {order.amount_total:.2f}，本次 {delta:+.2f}）。")
            order.amount_paid = new_paid

    # ---- 状态机 ----
    def action_confirm(self):
        for order in self:
            if order.state != 'draft':
                raise UserError("只有草稿订单可以确认。")
            if not order.line_ids:
                raise UserError("名单为空，不能确认。")
            order.departure_id.change_seats(len(order.line_ids))
            if not order.plan_ids:
                self.env['ta.receivable.plan'].create({
                    'order_id': order.id,
                    'name': '全额',
                    'due_date': order.departure_id.date_start,
                    'amount': order.amount_total,
                })
            order.state = 'confirmed'

    def action_trip(self):
        for order in self:
            if order.state != 'confirmed':
                raise UserError("只有已确认订单可进入行程中。")
            order.state = 'tripping'

    def action_settle(self):
        for order in self:
            if order.state != 'tripping':
                raise UserError("只有行程中的订单可以结算。")
            if order.amount_open > 0.01:
                raise UserError(f"仍有未到账 {order.amount_open:.2f}，不能结算。")
            order.state = 'settled'

    def action_cancel(self):
        for order in self:
            if order.state == 'settled':
                raise UserError("已结算订单不可取消。")
            if order.amount_paid > 0:
                raise UserError("订单已有认领到账，先走反审核再取消。")
            if not order.seats_released and order.state != 'draft':
                order.departure_id.change_seats(-len(order.line_ids))
                order.seats_released = True
            order.state = 'cancel'


class TaOrderLine(models.Model):
    _name = 'ta.order.line'
    _description = '报名名单行'
    _order = 'order_id, sequence'
    _inherit = ['ta.mixin']

    order_id = fields.Many2one('ta.order', string='订单', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='姓名', required=True)
    id_card = fields.Char(string='证件号')
    phone = fields.Char()
    kind = fields.Selection([
        ('adult', '成人'),
        ('child', '儿童'),
        ('child_bed', '儿童含床'),
        ('single', '单房差'),
        ('same_tour', '同团升级'),
    ], string='价别', default='adult', required=True)
    unit_price = fields.Float(digits=(12, 2),
                              compute='_compute_unit_price', store=True, readonly=False)
    amount = fields.Float(compute='_compute_amount', store=True, digits=(12, 2))

    @api.depends('kind', 'order_id.route_id')
    def _compute_unit_price(self):
        for line in self:
            route = line.order_id.route_id
            if not route or line.unit_price:
                continue
            price = route.price_ids.filtered(
                lambda p, k=line.kind: p.kind == k and p.active)
            line.unit_price = min(price.mapped('amount'), default=0.0)

    @api.depends('unit_price')
    def _compute_amount(self):
        for line in self:
            line.amount = line.unit_price


class TaReceivablePlan(models.Model):
    _name = 'ta.receivable.plan'
    _description = '应收期次'
    _order = 'due_date, id'
    _inherit = ['ta.mixin']

    order_id = fields.Many2one('ta.order', string='订单', required=True, ondelete='cascade',
                               index=True)
    name = fields.Char(string='期次', required=True)
    due_date = fields.Date(string='到期日')
    amount = fields.Float(digits=(12, 2), required=True)
    amount_paid = fields.Float(string='已核销', readonly=True, copy=False,
                            default=0.0, digits=(12, 2))
    note = fields.Char()
    # claim_ids 字段及认领核销分配逻辑由 ta_finance 扩展（ta_receivable_plan.py），
    # 避免 ta_order 反向引用 ta.payment.claim 造成加载顺序问题。
