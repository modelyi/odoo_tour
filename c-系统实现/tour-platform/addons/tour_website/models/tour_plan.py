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

    def _sync_amounts_from_regs(self):
        """线上报名后汇总团金额（收入报价/未收款/人数 ← 报名明细）。

        同线路同班期多报名复用同一承载团，金额取 Σ regs（幂等重算，不叠加），
        保证确认成团后收入确认（_revenue_amount → in_com_quo_sum）与应收（sum_un_pay）有额可依。
        """
        self.ensure_one()
        regs = self.env['tour.plan.reg'].search([('plan_id', '=', self.id)])
        self.write({
            'in_com_quo_sum': round(sum(r.in_com_quo_sum or 0.0 for r in regs), 2),
            'sum_un_pay': round(sum(r.sum_un_pay or 0.0 for r in regs), 2),
            'guest_count': sum(r.guest_count or 0 for r in regs),
            'adult_num': sum(r.adult_num or 0 for r in regs),
            'child_num': sum(r.child_num or 0 for r in regs),
            'old_man_num': sum(r.old_man_num or 0 for r in regs),
            'student_num': sum(r.student_num or 0 for r in regs),
            'baby_num': sum(r.baby_num or 0 for r in regs),
        })
