# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.exceptions import ValidationError


class TourPlan(models.Model):
    _inherit = 'tour.plan'

    def action_start(self):
        for plan in self:
            plan._check_booking_before_start()
        return super().action_start()

    def _check_booking_before_start(self):
        """出团前置校验：核心资源预订需全部确认，房/门票需二次确认。
        是否阻断由系统参数 tour_operation.require_full_booking 配置（默认阻断）。"""
        self.ensure_one()
        bookings = self.env['tour.booking'].search([
            ('plan_id', '=', self.id),
            ('state', '!=', 'cancelled'),
        ])
        if not bookings:
            return
        problems = []
        rt_label = dict(self.env['tour.booking']._fields['resource_type'].selection)
        for rt in ('guide', 'vehicle', 'hotel', 'scenic'):
            for b in bookings.filtered(lambda bk: bk.resource_type == rt):
                if b.state != 'confirmed':
                    problems.append('%s 预订 %s 未确认' % (rt_label.get(rt, rt), b.name))
                elif rt in ('hotel', 'scenic') and b.confirm_state != 'confirmed':
                    problems.append('%s 预订 %s 未二次确认' % (rt_label.get(rt, rt), b.name))
        if not problems:
            return
        msg = '出团前置校验未通过：\n' + '\n'.join(problems)
        require = self.env['ir.config_parameter'].sudo().get_param(
            'tour_operation.require_full_booking', 'True')
        if require == 'False':
            self.message_post(body='⚠️ ' + msg)
        else:
            raise ValidationError(msg)
