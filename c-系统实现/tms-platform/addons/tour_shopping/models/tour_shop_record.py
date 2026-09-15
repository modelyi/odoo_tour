# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourShopRecord(models.Model):
    _name = 'tour.shop.record'
    _description = '购物记录'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'shop_date desc, id desc'

    name = fields.Char('购物记录编号', required=True, copy=False, default='新建')

    # === 关联 ===
    plan_id = fields.Many2one('tour.plan', string='团队订单', required=True,
                              index=True, ondelete='restrict')
    plan_code = fields.Char('团号', related='plan_id.plan_code', store=True)
    shop_id = fields.Many2one('tour.supplier', string='购物店', required=True,
                              index=True, domain=[('sup_type', '=', 'shop')])
    supplier_name = fields.Char('购物店名称', related='shop_id.name', store=True)
    agreement_id = fields.Many2one('tour.shop.agreement', string='购物协议',
                                   domain="[('shop_id', '=', shop_id)]",
                                   help='返佣比例来源，选择后自动带出返佣比例')
    guide_id = fields.Many2one('tour.guide', string='带团导游', index=True)
    guide_name = fields.Char('导游姓名', related='guide_id.name', store=True)

    # === 明细 ===
    shop_date = fields.Date('购物日期', default=fields.Date.context_today,
                            index=True, required=True)
    guest_count = fields.Integer('参与购物客人数', required=True, default=1,
                                 help='≤ 团队 GuestCount')
    total_amount = fields.Float('购物总金额', digits=(15, 2), required=True,
                                help='团队在该购物店的消费总额')
    per_capita = fields.Float('人均购物', digits=(15, 2),
                              compute='_compute_per_capita', store=True,
                              help='= 购物总金额 / 参与购物客人数')
    commission_rate = fields.Float('返佣比例(%)', digits=(5, 2))
    commission_amount = fields.Float('返佣金额', digits=(16, 2),
                                     compute='_compute_commission', store=True,
                                     help='= 购物总金额 × 返佣比例 / 100')

    # === 商品明细行 ===
    item_lines = fields.One2many('tour.shop.record.line', 'record_id',
                                 string='商品明细')

    # === 状态 & 来源 ===
    state = fields.Selection([
        ('draft', '待确认'),
        ('confirmed', '已确认'),
        ('cancelled', '已退单'),
    ], string='状态', default='draft', required=True, index=True, tracking=True)
    source = fields.Selection([
        ('system', '系统录入'),
        ('app', 'APP录入'),
    ], string='来源', default='system', required=True)

    remark = fields.Text('备注')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)

    _uniq_shop_record = models.Constraint(
        'unique(plan_id, shop_id, shop_date)',
        '同一团队在同一天对同一购物店只能有一条购物记录',
    )

    @api.depends('total_amount', 'guest_count')
    def _compute_per_capita(self):
        for rec in self:
            if rec.guest_count:
                rec.per_capita = round(rec.total_amount / rec.guest_count, 2)
            else:
                rec.per_capita = 0.0

    @api.depends('total_amount', 'commission_rate')
    def _compute_commission(self):
        for rec in self:
            rec.commission_amount = round(
                (rec.total_amount or 0.0) * (rec.commission_rate or 0.0) / 100.0, 2)

    @api.onchange('shop_id')
    def _onchange_shop_id(self):
        if self.agreement_id and self.agreement_id.shop_id != self.shop_id:
            self.agreement_id = False

    @api.onchange('agreement_id')
    def _onchange_agreement_id(self):
        if self.agreement_id:
            self.commission_rate = self.agreement_id.rebate_rate

    @api.constrains('shop_id')
    def _check_shop_sup_type(self):
        for rec in self:
            if rec.shop_id and rec.shop_id.sup_type != 'shop':
                raise ValidationError('购物记录的购物店必须为 sup_type=shop 的供应商')

    @api.constrains('guest_count')
    def _check_guest_count(self):
        for rec in self:
            if rec.guest_count and rec.guest_count <= 0:
                raise ValidationError('参与购物客人数必须大于 0')

    @api.constrains('total_amount')
    def _check_total_amount(self):
        for rec in self:
            if rec.total_amount is not None and rec.total_amount < 0:
                raise ValidationError('购物总金额不能为负数')

    @api.constrains('shop_date', 'plan_id')
    def _check_shop_date_in_plan(self):
        for rec in self:
            if not (rec.plan_id and rec.shop_date):
                continue
            if rec.plan_id.begin_date and rec.shop_date < rec.plan_id.begin_date:
                raise ValidationError('购物日期不能早于团队出发日期')
            if rec.plan_id.end_date and rec.shop_date > rec.plan_id.end_date:
                raise ValidationError('购物日期不能晚于团队返回日期')

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})
