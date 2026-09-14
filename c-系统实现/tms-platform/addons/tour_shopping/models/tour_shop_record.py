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
    agreement_id = fields.Many2one('tour.shop.agreement', string='购物协议',
                                   domain="[('shop_id', '=', shop_id)]",
                                   help='返佣比例来源，选择后自动带出返佣比例')
    guide_id = fields.Many2one('tour.guide', string='带团导游', index=True)

    # === 明细 ===
    shop_date = fields.Date('购物日期', default=fields.Date.context_today, index=True)
    amount = fields.Float('购物金额', digits=(16, 2),
                          help='团队在该购物店的消费总额')
    commission_rate = fields.Float('返佣比例(%)', digits=(5, 2))
    commission_amount = fields.Float('返佣金额', digits=(16, 2),
                                     compute='_compute_commission', store=True,
                                     help='= 购物金额 × 返佣比例 / 100，团队利润来源')

    remark = fields.Text('备注')
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)

    _uniq_shop_record = models.Constraint(
        'unique(plan_id, shop_id, shop_date)',
        '同一团队在同一天对同一购物店只能有一条购物记录',
    )

    @api.depends('amount', 'commission_rate')
    def _compute_commission(self):
        for rec in self:
            rec.commission_amount = round(
                (rec.amount or 0.0) * (rec.commission_rate or 0.0) / 100.0, 2)

    @api.onchange('shop_id')
    def _onchange_shop_id(self):
        # 切换购物店时清空不匹配的协议
        if self.agreement_id and self.agreement_id.shop_id != self.shop_id:
            self.agreement_id = False

    @api.onchange('agreement_id')
    def _onchange_agreement_id(self):
        # 选择协议后自动带出返佣比例
        if self.agreement_id:
            self.commission_rate = self.agreement_id.rebate_rate

    @api.constrains('shop_id')
    def _check_shop_sup_type(self):
        for rec in self:
            if rec.shop_id and rec.shop_id.sup_type != 'shop':
                raise ValidationError('购物记录的购物店必须为 sup_type=shop 的供应商')

    @api.constrains('shop_date', 'plan_id')
    def _check_shop_date_in_plan(self):
        for rec in self:
            if not (rec.plan_id and rec.shop_date):
                continue
            if rec.plan_id.begin_date and rec.shop_date < rec.plan_id.begin_date:
                raise ValidationError('购物日期不能早于团队出发日期')
            if rec.plan_id.end_date and rec.shop_date > rec.plan_id.end_date:
                raise ValidationError('购物日期不能晚于团队返回日期')
