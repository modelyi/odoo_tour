# -*- coding: utf-8 -*-
"""product.template → tour.line 定位辅助（电商商品页 / 购物车识别线路产品）。"""
from odoo import models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_tour_line(self):
        """返回该产品模板对应的 tour.line（线路），非线路产品返回空记录。"""
        self.ensure_one()
        return self.env['tour.line'].sudo().search(
            [('product_tmpl_id', '=', self.id)], limit=1)
