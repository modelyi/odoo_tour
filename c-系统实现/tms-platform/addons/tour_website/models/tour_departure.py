# -*- coding: utf-8 -*-
"""tour.departure 扩展（GAP-4）。

补齐老人/学生/婴儿三档价格，与报名 5 类人数匹配；无值时回退线路模板价（tour.line）。
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TourDeparture(models.Model):
    _inherit = 'tour.departure'

    # GAP-4：价格档补齐（成人/儿童已有 price_adult/price_child）
    price_old_man = fields.Float('老人价', digits='Product Price')
    price_student = fields.Float('学生价', digits='Product Price')
    price_baby = fields.Float('婴儿价', digits='Product Price')

    def get_online_prices(self):
        """在线报名计价单价快照：发团计划价 → 线路模板价。

        返回 {'adult'/'child'/'old_man'/'student'/'baby': float}。
        """
        self.ensure_one()
        line = self.line_id
        return {
            'adult': self.price_adult if self.price_adult else (line.adult_price or 0.0),
            'child': self.price_child if self.price_child else (line.child_price or 0.0),
            'old_man': self.price_old_man if self.price_old_man else (line.old_man_price or 0.0),
            'student': self.price_student if self.price_student else (line.student_price or 0.0),
            'baby': self.price_baby if self.price_baby else (line.baby_price or 0.0),
        }

    @api.constrains('seats', 'booked_seats')
    def _check_seats_not_oversold(self):
        """兜底：已订位数不得超过总位数（并发下单防超卖）。"""
        for rec in self:
            if rec.seats and rec.booked_seats > rec.seats:
                raise ValidationError('班期「%s」已订位数超过总位数，余位不足' % rec.name)
