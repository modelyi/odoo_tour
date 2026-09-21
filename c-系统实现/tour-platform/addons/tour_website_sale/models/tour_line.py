# -*- coding: utf-8 -*-
"""tour.line 电商辅助：可报名班期列表（商品页班期选择器数据源）。"""
from odoo import fields, models


class TourLine(models.Model):
    _inherit = 'tour.line'

    def _website_available_departures(self):
        """已发布、未过期、有余位的发团计划（升序）。"""
        self.ensure_one()
        return self.env['tour.departure'].sudo().search([
            ('line_id', '=', self.id),
            ('state', '=', 'published'),
            ('start_date', '>=', fields.Date.today()),
            ('remain_seats', '>', 0),
        ], order='start_date asc')
