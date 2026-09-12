# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourShopAgreement(models.Model):
    _name = 'tour.shop.agreement'
    _description = '购物协议'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'begin_date desc, name'

    shop_id = fields.Many2one('res.partner', string='购物店', required=True,
                              index=True, domain=[('sup_type', '=', 'shop')])
    name = fields.Char('协议编号', required=True, index=True)
    shop_type = fields.Char('购物店类型', help='珠宝/特产/玉器等')
    rebate_rate = fields.Float('返佣比例(%)', digits=(5, 2))
    rebate_base = fields.Selection([
        ('turnover', '营业额'),
        ('profit', '利润'),
        ('headcount', '人头'),
    ], string='返佣基数')
    guarantee_rebate = fields.Float('保底返佣', digits=(16, 2))
    settle_cycle = fields.Selection([
        ('month', '月'),
        ('quarter', '季'),
        ('per_group', '单团'),
    ], string='结算周期')
    begin_date = fields.Date('协议生效日')
    end_date = fields.Date('协议到期日')
    state = fields.Selection([
        ('draft', '草稿'),
        ('effective', '生效'),
        ('expired', '到期'),
        ('terminated', '终止'),
    ], string='协议状态', default='draft', tracking=True)
    company_id = fields.Many2one('res.company', string='所属公司',
                                 default=lambda self: self.env.company)

    @api.constrains('shop_id')
    def _check_shop_sup_type(self):
        for rec in self:
            if rec.shop_id and rec.shop_id.sup_type != 'shop':
                raise ValidationError('购物协议的购物店必须为 sup_type=shop 的供应商')
