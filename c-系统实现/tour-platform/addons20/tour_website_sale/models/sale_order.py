# -*- coding: utf-8 -*-
"""sale.order 电商下单扩展。

- 购物车加购：识别「班期 + 五档人数」kwarg，服务端重校验余位、重算数量与单价
- 确认桥接：action_confirm 后把带班期的行桥接为 tour.plan.reg（复用 tour_website 共享方法）
- 财务口径：sale.order 只做销售/收款入口，不独立出账（tour.plan 为唯一口径）
"""
from odoo import _, fields, models
from odoo.exceptions import ValidationError


def _to_int(val):
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


TOUR_COUNT_FIELDS = ('adult_num', 'child_num', 'old_man_num', 'student_num', 'baby_num')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------------
    # 购物车：班期 + 人数
    # ------------------------------------------------------------------
    def _extract_tour_counts(self, kwargs):
        return {f: _to_int(kwargs.get(f)) for f in TOUR_COUNT_FIELDS}

    def _validate_tour_booking(self, departure, line, counts):
        """加购时服务端重校验（余位/班期状态/线路匹配），禁止客户端传价。"""
        total = sum(counts.values())
        if not departure:
            raise ValidationError(_('请选择发团日期'))
        if not line:
            raise ValidationError(_('该产品不是可报名的线路'))
        if departure.line_id.id != line.id:
            raise ValidationError(_('线路与班期不匹配'))
        if departure.state != 'published':
            raise ValidationError(_('该班期未发布，不可下单'))
        if departure.start_date < fields.Date.today():
            raise ValidationError(_('该班期已过期，不可下单'))
        if total <= 0:
            raise ValidationError(_('请至少填写 1 位人数'))
        if total > departure.remain_seats:
            raise ValidationError(_('余位不足（剩余 %s 位）') % departure.remain_seats)

    def _cart_find_product_line(
        self, product_id, uom_id, linked_line_id=False,
        no_variant_attribute_value_ids=None, **kwargs
    ):
        dep_id = _to_int(kwargs.get('departure_id'))
        if dep_id:
            # 线路行：同产品不同班期分属不同行
            return self.order_line.filtered_domain([
                ('product_id', '=', product_id),
                ('product_uom_id', '=', uom_id),
                ('departure_id', '=', dep_id),
            ])
        return super()._cart_find_product_line(
            product_id, uom_id, linked_line_id=linked_line_id,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids, **kwargs)

    def _prepare_order_line_values(
        self, product_id, quantity, uom_id, *, linked_line_id=False,
        no_variant_attribute_value_ids=None, product_custom_attribute_values=None,
        combo_item_id=None, **kwargs
    ):
        values = super()._prepare_order_line_values(
            product_id, quantity, uom_id, linked_line_id=linked_line_id,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            product_custom_attribute_values=product_custom_attribute_values,
            combo_item_id=combo_item_id, **kwargs)
        dep_id = _to_int(kwargs.get('departure_id'))
        if not dep_id:
            return values
        product = self.env['product.product'].browse(product_id)
        departure = self.env['tour.departure'].sudo().browse(dep_id).exists()
        line = product.product_tmpl_id._get_tour_line()
        counts = self._extract_tour_counts(kwargs)
        self._validate_tour_booking(departure, line, counts)
        values.update({
            'departure_id': departure.id,
            'adult_num': counts['adult_num'],
            'child_num': counts['child_num'],
            'old_man_num': counts['old_man_num'],
            'student_num': counts['student_num'],
            'baby_num': counts['baby_num'],
            'product_uom_qty': sum(counts.values()),
            'name': '%s %s' % (product.product_tmpl_id.name, departure.start_date),
        })
        return values

    def _prepare_order_line_update_values(self, order_line, quantity, **kwargs):
        values = super()._prepare_order_line_update_values(order_line, quantity, **kwargs)
        if not (order_line.departure_id or _to_int(kwargs.get('departure_id'))):
            return values  # 非线路行
        dep_id = _to_int(kwargs.get('departure_id'))
        if dep_id:
            departure = self.env['tour.departure'].sudo().browse(dep_id).exists()
            counts = self._extract_tour_counts(kwargs)
            self._validate_tour_booking(departure, order_line._get_tour_line(), counts)
            values.update({
                'departure_id': departure.id,
                'name': '%s %s' % (
                    order_line.product_id.product_tmpl_id.name, departure.start_date),
                'product_uom_qty': sum(counts.values()),
                'adult_num': counts['adult_num'],
                'child_num': counts['child_num'],
                'old_man_num': counts['old_man_num'],
                'student_num': counts['student_num'],
                'baby_num': counts['baby_num'],
            })
        else:
            # 纯数量变更（购物车步进器对线路行无意义）：数量恒等于人数档合计，忽略步进
            values.pop('product_uom_qty', None)
        return values

    # ------------------------------------------------------------------
    # 确认桥接：sale.order → tour.plan.reg
    # ------------------------------------------------------------------
    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            if order.state == 'sale':
                order._create_plan_regs_from_order()
        return res

    def _create_plan_regs_from_order(self):
        """确认后把带班期的行桥接为报名（财务唯一口径 tour.plan，sale 不独立出账）。"""
        self.ensure_one()
        for line in self.order_line.filtered(
                lambda l: l.departure_id and not l.reg_id):
            line._bridge_to_plan_reg()
