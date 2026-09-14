# -*- coding: utf-8 -*-
"""tour.line 官网展示辅助：起价计算（班期价 → 线路模板价）。"""
from odoo import api, fields, models


class TourLine(models.Model):
    _inherit = 'tour.line'

    @api.model
    def website_price_map(self, lines):
        """官网起价 {line_id: float}。

        优先取该线路「已发布、未过期、有余位」发团计划的最低成人价；
        无发团计划时回退线路模板成人价 list_price（委托 product.template）。
        两者皆无则不返回该 key（前端显示「价格电询」）。
        """
        if not lines:
            return {}
        today = fields.Date.today()
        departures = self.env['tour.departure'].sudo().search([
            ('line_id', 'in', lines.ids),
            ('state', '=', 'published'),
            ('start_date', '>=', today),
            ('remain_seats', '>', 0),
        ])
        price_map = {}
        for dep in departures:
            p = dep.price_adult if dep.price_adult else (dep.line_id.list_price or 0.0)
            if p > 0 and (dep.line_id.id not in price_map or p < price_map[dep.line_id.id]):
                price_map[dep.line_id.id] = p
        for line in lines:
            if line.id not in price_map and line.list_price and line.list_price > 0:
                price_map[line.id] = line.list_price
        return price_map
