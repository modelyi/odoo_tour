# -*- coding: utf-8 -*-
"""官网线路展示 + 在线报名 Controller（B2C 最小闭环）。

安全要点：
- auth='public'：未登录可访问
- 读操作：sudo() + 严格过滤（active / audit_state / state / remain_seats）
- 写操作：全部收敛到 tour.plan.reg.create_online_reg() 单一入口，校验在模型方法内
- POST 路由保持默认 csrf=True（不设 csrf=False）
"""
from odoo import fields, http
from odoo.exceptions import ValidationError
from odoo.http import request

PASSENGER_SLOTS = 8  # 报名表单预渲染的证件录入行数


class TourWebsite(http.Controller):

    # ---------- 线路列表 ----------
    @http.route('/tours', type='http', auth='public', website=True, sitemap=True)
    def tour_list(self, **kw):
        TourLine = request.env['tour.line'].sudo()
        domain = [('active', '=', True), ('audit_state', '=', 'approved')]

        categ_id = kw.get('categ_id')
        if categ_id:
            try:
                domain.append(('categ_id', '=', int(categ_id)))
            except (TypeError, ValueError):
                pass

        keyword = (kw.get('keyword') or '').strip()
        if keyword:
            domain += ['|', ('name', 'ilike', keyword), ('help_code', 'ilike', keyword)]

        lines = TourLine.search(domain, order='sequence, name')
        categories = request.env['product.category'].sudo().search(
            [], order='complete_name')
        # 起价 = 该线路已发布且未过期发团计划的最低成人价（无则回退线路成人价；均无显示「价格电询」）
        price_from = TourLine.website_price_map(lines)
        return request.render('tour_website.tour_list', {
            'lines': lines,
            'categories': categories,
            'keyword': keyword,
            'categ_id': categ_id,
            'price_from': price_from,
        })

    # ---------- 线路详情 ----------
    @http.route('/tours/<int:line_id>', type='http', auth='public', website=True)
    def tour_detail(self, line_id, **kw):
        line = request.env['tour.line'].sudo().browse(line_id).exists()
        if not line or not line.active or line.audit_state != 'approved':
            return request.not_found()

        departures = request.env['tour.departure'].sudo().search([
            ('line_id', '=', line.id),
            ('state', '=', 'published'),
            ('start_date', '>=', fields.Date.today()),
        ], order='start_date asc')
        details = request.env['tour.line.detail'].sudo().search([
            ('line_id', '=', line.id),
        ], order='day_no asc, sequence asc, id asc')
        return request.render('tour_website.tour_detail', {
            'line': line,
            'departures': departures,
            'details': details,
        })

    # ---------- 报名表单页 ----------
    @http.route('/tours/<int:line_id>/register', type='http', auth='public',
                website=True, methods=['GET'])
    def tour_register_form(self, line_id, **kw):
        line = request.env['tour.line'].sudo().browse(line_id).exists()
        if not line or not line.active or line.audit_state != 'approved':
            return request.not_found()

        departure = request.env['tour.departure'].sudo().browse(
            self._int(kw.get('departure_id'))).exists()
        error = self._departure_error(departure, line)
        return request.render('tour_website.tour_register', {
            'line': line,
            'departure': departure,
            'error': error,
            'post': {},
            'slots': list(range(PASSENGER_SLOTS)),
        })

    # ---------- 报名提交 ----------
    @http.route('/tours/<int:line_id>/register', type='http', auth='public',
                website=True, methods=['POST'], csrf=True)
    def tour_register_submit(self, line_id, **post):
        line = request.env['tour.line'].sudo().browse(line_id).exists()
        departure = request.env['tour.departure'].sudo().browse(
            self._int(post.get('departure_id'))).exists()
        if not line or not departure:
            return request.not_found()

        passengers = self._parse_passengers(post)
        try:
            partner_id = (request.env.user.partner_id.id
                          if not request.env.user._is_public() else None)
            reg = request.env['tour.plan.reg'].sudo().create_online_reg(
                line, departure, post, passengers=passengers,
                partner_id=partner_id)
        except ValidationError as exc:
            return request.render('tour_website.tour_register', {
                'line': line,
                'departure': departure,
                'error': str(exc),
                'post': post,
                'slots': list(range(PASSENGER_SLOTS)),
            })
        return request.redirect('/tours/register/success/%s' % reg.id)

    # ---------- 报名成功页 ----------
    @http.route('/tours/register/success/<int:reg_id>', type='http',
                auth='public', website=True)
    def tour_register_success(self, reg_id, **kw):
        reg = request.env['tour.plan.reg'].sudo().browse(reg_id).exists()
        if not reg:
            return request.not_found()
        return request.render('tour_website.tour_register_success', {'reg': reg})

    # ---------- helpers ----------
    @staticmethod
    def _int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _departure_error(self, departure, line):
        if not departure:
            return None
        if departure.line_id.id != line.id:
            return '线路与班期不匹配，请重新选择发团日期'
        if departure.state != 'published':
            return '该班期未发布，不可报名'
        if departure.start_date < fields.Date.today():
            return '该班期已过期，不可报名'
        if departure.remain_seats <= 0:
            return '该班期已满，不可报名'
        return None

    def _parse_passengers(self, post):
        """从 indexed 表单字段解析逐人证件。"""
        passengers = []
        i = 0
        while True:
            key = 'passenger_name_%d' % i
            if key not in post:
                break
            name = (post.get(key) or '').strip()
            id_number = (post.get('passenger_id_number_%d' % i) or '').strip()
            if name or id_number:
                passengers.append({
                    'name': name,
                    'passenger_type': post.get('passenger_type_%d' % i, 'adult'),
                    'id_type': post.get('passenger_id_type_%d' % i, 'id_card'),
                    'id_number': id_number,
                })
            i += 1
        return passengers
