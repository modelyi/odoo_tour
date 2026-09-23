# -*- coding: utf-8 -*-
from odoo import models, fields


class TourPayWay(models.Model):
    _name = 'tour.pay.way'
    _description = '收付场景'
    _order = 'sequence, id'

    name = fields.Char('名称', required=True, index=True)
    code = fields.Char('编码', index=True)
    # 收付场景只区分「是否挂账」（决定是否即时收付/是否走资金账户校验）；
    # 具体资金走哪个账户由 tour.pay.channel（支付渠道）负责，二者解耦。
    is_credit = fields.Boolean('挂账（非即时收付）', default=False,
                               help='勾选表示挂账/月结等非即时收付场景（如签单），'
                                    '此类收款不产生即时资金流动，跳过资金账户校验')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('启用', default=True)
    brief = fields.Text('摘要')
