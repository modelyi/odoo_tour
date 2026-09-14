# -*- coding: utf-8 -*-
"""线路电商下单 Controller：商品页「选班期 + 填人数」→ 购物车。

不走 website_sale 默认 JSON-RPC 加购（其前端只透传 product_id/qty），改用
HTTP POST 到本路由，把 departure_id + 五档人数交给 sale.order._cart_add，
服务端重校验余位、重算数量与单价。其余购物车/结账流程仍走 website_sale 原生。
"""
from urllib.parse import quote

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

TOUR_COUNT_FIELDS = ('adult_num', 'child_num', 'old_man_num', 'student_num', 'baby_num')


class TourWebsiteSale(http.Controller):

    @http.route('/shop/tour/add', type='http', auth='public', website=True,
                methods=['POST'], csrf=True, sitemap=False)
    def tour_add_to_cart(self, **post):
        product_id = self._int(post.get('product_id'))
        departure_id = self._int(post.get('departure_id'))
        counts = {f: self._int(post.get(f)) for f in TOUR_COUNT_FIELDS}
        product = request.env['product.product'].sudo().browse(product_id).exists()
        if not product:
            return request.not_found()

        # 服务端二次校验（前端只读，不信任客户端任何字段/价格）
        order_sudo = request.cart or request.website._create_cart()
        try:
            order_sudo._cart_add(
                product_id=product_id,
                quantity=sum(counts.values()),
                departure_id=departure_id,
                **counts,
            )
        except ValidationError as exc:
            url = product.product_tmpl_id._get_product_url()
            return request.redirect('%s?tour_error=%s' % (url, quote(str(exc))))

        return request.redirect('/shop/cart')

    @staticmethod
    def _int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
