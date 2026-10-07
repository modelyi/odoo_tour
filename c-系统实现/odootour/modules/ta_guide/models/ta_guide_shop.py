# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, AccessError


class TaShop(models.Model):
    """购物记录（BS-08 §4.1）：导游 APP 录入 / 计调系统补录 → 会计确认 → 退单（§4.2 简化）。
    确认时按购物协议幂等生成/重算导游佣金单（§4.9）。补单（§4.3）＝新建购物记录
    （source=系统录入、原因入备注），确认即审核（确认人 ≠ 导游，职务分离）。
    """
    _name = 'ta.shop'
    _description = '购物记录'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'shop_date desc, id desc'

    name = fields.Char(string='购物单号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.shop') or '/')
    departure_id = fields.Many2one(
        'ta.departure', string='发团计划', required=True, tracking=True,
        domain="[('state', 'in', ('confirmed', 'departed', 'settled'))]")
    plan_code = fields.Char(related='departure_id.code', string='计划号')
    shop_partner_id = fields.Many2one(
        'res.partner', string='购物店', required=True, tracking=True,
        domain="[('supplier_rank', '>', 0)]")
    shop_name = fields.Char(related='shop_partner_id.name', string='购物店名称')
    shop_date = fields.Date(string='购物日期', required=True,
                            default=fields.Date.context_today, tracking=True)
    guest_count = fields.Integer(string='参与购物客人数', required=True, default=1,
                                 help='≤ 团队客人数（BS-08 GuestCount）。')
    total_amount = fields.Float(string='购物总金额', required=True, digits=(15, 2), tracking=True)
    per_capita = fields.Float(string='人均购物', compute='_compute_per_capita', digits=(15, 2),
                              help='= 购物总金额 ÷ 参与购物客人数（BS-08 §4.1）。')
    guide_id = fields.Many2one('res.partner', string='导游', required=True, tracking=True,
                               default=lambda self: self.env.user.partner_id)
    guide_name = fields.Char(related='guide_id.name', string='导游姓名')
    item_line_ids = fields.One2many('ta.shop.item', 'shop_id', string='商品明细')
    source = fields.Selection([
        ('app', 'APP录入'),
        ('sys', '系统录入'),
    ], string='来源', required=True, default='sys', tracking=True)
    remark = fields.Text(string='备注', help='补单原因（BS-08 §4.3）等录入说明。')
    state = fields.Selection([
        ('draft', '待确认'),
        ('confirmed', '已确认'),
        ('returned', '已退单'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    return_date = fields.Date(string='退单日期', readonly=True, copy=False)
    return_reason = fields.Text(string='退单原因', copy=False,
                                help='退单时必填 [内控-审计轨迹]。')

    @api.depends('total_amount', 'guest_count')
    def _compute_per_capita(self):
        for s in self:
            s.per_capita = round(s.total_amount / s.guest_count, 2) if s.guest_count else 0.0

    @api.constrains('total_amount', 'guest_count')
    def _check_positive_amounts(self):
        for s in self:
            if s.total_amount <= 0:
                raise UserError("购物总金额必须大于 0。")
            if s.guest_count <= 0:
                raise UserError("参与购物客人数必须大于 0。")

    def _team_heads(self):
        """团队客人数（BS-08 GuestCount）：已确认/行程中/已结算订单人数，兜底发团报名数。"""
        self.ensure_one()
        heads = sum(self.env['ta.order'].search([
            ('departure_id', '=', self.departure_id.id),
            ('state', 'in', ('confirmed', 'tripping', 'settled')),
        ]).mapped('heads'))
        return heads or self.departure_id.seats_used

    @api.constrains('guest_count', 'departure_id')
    def _check_guest_count(self):
        for s in self:
            heads = s._team_heads()
            if heads and s.guest_count > heads:
                raise UserError(f"参与购物客人数 {s.guest_count} 超过团队客人数 {heads}。")

    def action_confirm(self):
        """会计确认（职务分离：确认人 ≠ 导游）；确认后按购物协议幂等生成/重算佣金单。"""
        for s in self:
            if s.state != 'draft':
                raise UserError("只有待确认的购物记录可以确认。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("购物确认需要会计权限。")
            if s.guide_id == self.env.user.partner_id:
                raise AccessError("确认人不能是带团导游本人。")
            s.state = 'confirmed'
            commission = self.env['ta.guide.commission']._upsert_from_shop_group(s)
            if commission:
                s.message_post(body=f"已生成/更新佣金单 {commission.name}。")
            else:
                s.message_post(body="该购物店无生效返佣协议（或佣金单已确认/已结算），未生成新佣金单。")
        return True

    def action_return(self):
        """退单（BS-08 §4.2 简化）：会计操作、原因必填；关联草稿佣金单取消并按剩余
        已确认记录重算；已确认/已结算佣金单拦截，提示红字发票与个税抵扣处理。"""
        for s in self:
            if s.state != 'confirmed':
                raise UserError("只有已确认的购物记录可以退单。")
            if not self.env.user.has_group('ta_base.group_ta_accountant'):
                raise AccessError("退单需要会计权限。")
            if not s.return_reason:
                raise UserError("退单原因必填。")
            commissions = self.env['ta.guide.commission'].search([
                ('departure_id', '=', s.departure_id.id),
                ('shop_partner_id', '=', s.shop_partner_id.id),
            ])
            if any(c.state in ('confirmed', 'settled') for c in commissions):
                raise UserError(
                    "该购物店的佣金单已确认/已结算，不能直接退单：请先由会计处理"
                    "红字发票与已代扣个税抵扣（BS-08 §4.2）。")
            commissions.filtered(lambda c: c.state == 'draft').write({'state': 'cancel'})
            s.state = 'returned'
            s.return_date = fields.Date.context_today(s)
            remaining = self.env['ta.shop'].search([
                ('departure_id', '=', s.departure_id.id),
                ('shop_partner_id', '=', s.shop_partner_id.id),
                ('state', '=', 'confirmed'),
            ])
            if remaining:
                self.env['ta.guide.commission']._upsert_from_shop_group(remaining[0])
        return True


class TaShopItem(models.Model):
    """购物商品明细行（BS-08 §4.1 可选）。"""
    _name = 'ta.shop.item'
    _description = '购物商品明细'
    _inherit = ['ta.mixin']

    shop_id = fields.Many2one('ta.shop', ondelete='cascade', required=True)
    name = fields.Char(string='商品名称', required=True)
    quantity = fields.Integer(string='数量', default=1, required=True)
    unit_price = fields.Float(string='单价', digits=(15, 2))
    amount = fields.Float(string='金额', compute='_compute_amount', digits=(15, 2))

    @api.depends('quantity', 'unit_price')
    def _compute_amount(self):
        for line in self:
            line.amount = round(line.quantity * line.unit_price, 2)


class TaShopAgreement(models.Model):
    """购物店返佣协议（BS-08 §4.5）：基础返佣比例 + 人均阶梯规则；佣金引擎据此定比例。"""
    _name = 'ta.shop.agreement'
    _description = '购物店返佣协议'
    _inherit = ['mail.thread', 'ta.mixin']
    _order = 'begin_date desc, id desc'

    name = fields.Char(string='协议编号', readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('ta.shop.agreement') or '/')
    shop_partner_id = fields.Many2one(
        'res.partner', string='购物店', required=True, tracking=True,
        domain="[('supplier_rank', '>', 0)]")
    shop_name = fields.Char(related='shop_partner_id.name', string='购物店名称')
    begin_date = fields.Date(string='协议开始日期', required=True, tracking=True)
    end_date = fields.Date(string='协议结束日期', required=True, tracking=True)
    base_rate = fields.Float(string='基础返佣比例(%)', required=True, digits=(5, 2), tracking=True,
                             help='无阶梯规则命中时使用（BS-08 §4.5）。')
    tier_rule_ids = fields.One2many('ta.shop.agreement.tier', 'agreement_id', string='阶梯规则')
    state = fields.Selection([
        ('draft', '草稿'),
        ('active', '生效'),
        ('expired', '已过期'),
    ], string='状态', default='draft', required=True, tracking=True, copy=False)
    note = fields.Char()

    @api.constrains('begin_date', 'end_date')
    def _check_dates(self):
        for a in self:
            if a.end_date <= a.begin_date:
                raise UserError("协议结束日期必须晚于开始日期。")

    def action_active(self):
        for a in self:
            if a.state != 'draft':
                raise UserError("只有草稿协议可以生效。")
            a.state = 'active'

    def action_expire(self):
        for a in self:
            if a.state != 'active':
                raise UserError("只有生效协议可以置为已过期。")
            a.state = 'expired'

    def _get_rate(self, per_capita, shop_date):
        """BS-08 §4.5 业务规则：协议有效期内按人均购物匹配阶梯，无匹配用基础比例。"""
        self.ensure_one()
        shop_date = fields.Date.to_date(shop_date)
        if self.state != 'active' or not (self.begin_date <= shop_date <= self.end_date):
            return 0.0
        for tier in self.tier_rule_ids.sorted('min_per_capita'):
            if per_capita >= tier.min_per_capita and (
                    not tier.max_per_capita or per_capita < tier.max_per_capita):
                return tier.commission_rate
        return self.base_rate


class TaShopAgreementTier(models.Model):
    """购物协议阶梯规则（BS-08 §4.5）：人均购物区间对应返佣比例。"""
    _name = 'ta.shop.agreement.tier'
    _description = '购物协议阶梯规则'
    _inherit = ['ta.mixin']
    _order = 'min_per_capita, id'

    agreement_id = fields.Many2one('ta.shop.agreement', ondelete='cascade', required=True)
    min_per_capita = fields.Float(string='人均购物下限', required=True, digits=(15, 2))
    max_per_capita = fields.Float(string='人均购物上限', digits=(15, 2),
                                  help='留空表示无上限。')
    commission_rate = fields.Float(string='返佣比例(%)', required=True, digits=(5, 2))

    @api.constrains('min_per_capita', 'max_per_capita')
    def _check_range(self):
        for t in self:
            if t.max_per_capita and t.max_per_capita <= t.min_per_capita:
                raise UserError("阶梯上限必须大于下限。")
