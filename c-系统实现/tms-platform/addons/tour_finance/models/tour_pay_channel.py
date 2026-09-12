# -*- coding: utf-8 -*-
from odoo import models, fields


class TourPayChannel(models.Model):
    _name = 'tour.pay.channel'
    _description = '支付渠道'
    _order = 'sequence, id'

    name = fields.Char('渠道名称', required=True, index=True)
    channel_type = fields.Selection([
        ('bank_transfer', '银行转账'),
        ('wechat', '微信'),
        ('alipay', '支付宝'),
        ('cash', '现金'),
        ('other', '其他'),
    ], string='渠道类型', required=True, index=True)
    fund_account_code = fields.Char('资金账户编码',
                                    help='1002 银行存款 / 1012 其他货币资金 / 1001 库存现金')
    fund_account_name = fields.Char('资金账户名称')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True)
    brief = fields.Text('摘要')
    company_id = fields.Many2one('res.company', string='公司',
                                 default=lambda self: self.env.company)

    _uniq_channel_type = models.Constraint(
        'unique(channel_type)',
        '支付渠道类型已存在',
    )
