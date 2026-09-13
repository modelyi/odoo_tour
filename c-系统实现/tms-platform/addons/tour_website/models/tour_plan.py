# -*- coding: utf-8 -*-
"""tour.plan 扩展（GAP-1 / GAP-3）。

GAP-1：新增 departure_id 回链 tour.departure，线上报名时按「线路 + 班期」定位/创建承载团队。
GAP-3：from_type 追加「6 线上官网」渠道标识（业绩归属 + 财务认领定位）。
"""
from odoo import fields, models


class TourPlan(models.Model):
    _inherit = 'tour.plan'

    # GAP-1：发团计划（tour.departure）回链；仅线上发布计划回填，可空
    departure_id = fields.Many2one(
        'tour.departure', string='发团计划', index=True, ondelete='set null',
        help='线上发布的发团计划（tour.departure）回链，一个已发布班期对应一个团队订单')

    # GAP-3：订单来源追加线上官网渠道
    from_type = fields.Selection(
        selection_add=[('6', '线上官网')])
