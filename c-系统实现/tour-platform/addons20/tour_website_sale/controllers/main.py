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
        # 20 删掉了 `request.website`（19 在 website/models/ir_http.py:265 赋的值），
        # 改由 Environment 提供 `env.website`（odoo/orm/environments.py:303）。
        # **这条不能回落到 19**：19 的 Environment 上没有 website 属性。
        #
        # 班期/人数必须**在进购物车之前**判掉：`_prepare_order_line_values` 对
        # `departure_id` 为空是"当普通产品行放行"（普通商品要能走同一条覆盖），
        # 所以缺班期不会报错，反而会静默加出一行没有班期的线路产品；人数全 0 时
        # `quantity=0` 在 20 的 `_cart_update` 里是"删行/无操作"，也不进校验。
        # 两种都表现为"加购成功"（303 → /shop/cart），只有负例冒烟看得见。
        # 私有 helper 带模块前缀：门户控制器会被 `build_controllers()` 合并成
        # 一个类，同名 helper 互相遮蔽（见 TDS-30 §5.8 #21）。
        if not departure_id:
            return self._tour_booking_error(product, '请选择发团日期')
        if sum(counts.values()) <= 0:
            return self._tour_booking_error(product, '请至少填写 1 位人数')

        order_sudo = request.cart or request.env.website._create_cart()
        try:
            order_sudo._cart_add(
                product_id=product_id,
                quantity=sum(counts.values()),
                departure_id=departure_id,
                **counts,
            )
        except ValidationError as exc:
            return self._tour_booking_error(product, str(exc))

        return request.redirect('/shop/cart')

    @staticmethod
    def _tour_booking_error(product, message):
        """回商品页并带 `?tour_error=`（模板里渲染成 alert）。"""
        url = product.product_tmpl_id._get_product_url()
        return request.redirect('%s?tour_error=%s' % (url, quote(message)))

    @staticmethod
    def _int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
