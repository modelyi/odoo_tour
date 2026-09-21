# -*- coding: utf-8 -*-
"""sale.order.line 扩展：班期 + 五档人数 + 班期价计价。

电商下单时班期必选，人数按五档填写；单价服务端重算（departure.get_online_prices），
前端只读展示，禁止客户端传价。sale.order 仅做销售/收款入口，不独立出账。
"""
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # === 班期 + 人数（电商下单必填项） ===
    departure_id = fields.Many2one(
        'tour.departure', string='发团班期', index=True, ondelete='set null',
        help='下单所选的发团计划（tour.departure），班期必选')
    adult_num = fields.Integer('成人数', default=1)
    child_num = fields.Integer('儿童数', default=0)
    old_man_num = fields.Integer('老人数', default=0)
    student_num = fields.Integer('学生数', default=0)
    baby_num = fields.Integer('婴儿数', default=0)

    # === 桥接回链 ===
    reg_id = fields.Many2one(
        'tour.plan.reg', string='桥接报名', index=True, ondelete='set null',
        readonly=True, copy=False,
        help='sale.order 确认后桥接生成的 tour.plan.reg（财务唯一口径）')

    total_people = fields.Integer('总人数', compute='_compute_total_people',
                                  store=False,
                                  help='成人+儿童+老人+学生+婴儿')

    @api.depends('adult_num', 'child_num', 'old_man_num', 'student_num', 'baby_num')
    def _compute_total_people(self):
        for line in self:
            line.total_people = (line.adult_num + line.child_num + line.old_man_num
                                 + line.student_num + line.baby_num)

    def _get_tour_line(self):
        """线路产品（product.template → tour.line）。"""
        self.ensure_one()
        if not self.product_id:
            return self.env['tour.line']
        return self.product_id.product_tmpl_id._get_tour_line()

    def _is_tour_booking_line(self):
        """是否为带班期的线路下单行。"""
        self.ensure_one()
        return bool(self.departure_id)

    def _get_quote(self):
        """五档价 × 人数 = 行报价（服务端重算，禁止客户端传价）。"""
        self.ensure_one()
        if not self.departure_id:
            return 0.0
        prices = self.departure_id.get_online_prices()
        return (self.adult_num * prices['adult'] + self.child_num * prices['child']
                + self.old_man_num * prices['old_man']
                + self.student_num * prices['student']
                + self.baby_num * prices['baby'])

    def _get_display_price_ignore_combo(self):
        """班期行单价 = 总报价 / 总人数（服务端重算，不参与价目表）。"""
        self.ensure_one()
        if self._is_tour_booking_line():
            total = self.total_people
            if total > 0:
                return self._get_quote() / total
        return super()._get_display_price_ignore_combo()

    @api.depends('product_id', 'company_id', 'departure_id')
    def _compute_tax_ids(self):
        """线路电商行不计税：财务唯一口径在 tour.plan，sale.order 不独立出账。"""
        tour_lines = self.filtered('departure_id')
        for line in tour_lines:
            line.tax_ids = False
        others = self - tour_lines
        if others:
            super(SaleOrderLine, others)._compute_tax_ids()

    # ------------------------------------------------------------------
    # 桥接：sale.order.line → tour.plan.reg（复用 tour_website 共享服务方法）
    # ------------------------------------------------------------------
    def _bridge_to_plan_reg(self):
        """将本行桥接为 tour.plan.reg，回写 reg_id（幂等：已有 reg_id 则跳过）。"""
        self.ensure_one()
        if not self.departure_id or self.reg_id:
            return None
        line = self._get_tour_line()
        if not line:
            return None
        counts = {
            'adult_num': self.adult_num,
            'child_num': self.child_num,
            'old_man_num': self.old_man_num,
            'student_num': self.student_num,
            'baby_num': self.baby_num,
        }
        partner = self.order_id.partner_id
        mobile = (partner.mobile if 'mobile' in partner._fields else '') \
            or partner.phone or ''
        contact = {
            'name': partner.name or '',
            'mobile': mobile,
            'supplier_user': partner.name or '',
            'tel': partner.phone or '',
            'occupation': '',
            'nation': '',
            'province': '',
            'city_name': '',
            'remark': '电商订单 %s' % self.order_id.name,
        }
        reg = self.env['tour.plan.reg'].sudo()._create_plan_reg_from_order(
            line, self.departure_id, counts, contact,
            passengers=None,
            from_type='7', source_label='电商下单',
            require_valid_mobile=False,
            sale_order_line=self,
        )
        self.reg_id = reg.id
        return reg
