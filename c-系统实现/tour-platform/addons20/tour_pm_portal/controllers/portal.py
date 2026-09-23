# -*- coding: utf-8 -*-
"""产品经理门户控制器 — 班期作战室。

核心路由：
- /my/pm                     班期作战室（日历 + 预警 + 操作）
- /my/pm/lines/<int:line_id> 线路详情（单线路全景）
- /my/pm/departure/<int:dep_id>/action  班期操作（调价/取消/加位）
"""
import datetime
import json

from odoo import _, fields, http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class PortalPM(CustomerPortal):

    def _is_pm_user(self):
        pm_group = request.env.ref('tour_pm_portal.group_pm_portal', raise_if_not_found=False)
        if not pm_group:
            return False
        return pm_group in request.env.user.group_ids

    def _get_pm_context(self):
        return {'pm_portal': True}

    # ------------------------------------------------------------------
    # /my/pm — 班期作战室
    # ------------------------------------------------------------------
    @http.route(['/my/pm', '/my/pm/home'], type='http', auth='user', website=True)
    def pm_war_room(self, month=None, **kw):
        """班期作战室：日历视图 + 预警 + 快捷操作。"""
        if not self._is_pm_user():
            return request.render('tour_pm_portal.portal_pm_no_access')

        env = request.env
        Departure = env['tour.departure'].sudo()
        today = fields.Date.today()

        if month:
            try:
                view_date = datetime.datetime.strptime(month + '-01', '%Y-%m-%d').date()
            except ValueError:
                view_date = today.replace(day=1)
        else:
            view_date = today.replace(day=1)

        month_start = view_date
        month_end = month_start + datetime.timedelta(days=32)
        month_end = month_end.replace(day=1) - datetime.timedelta(days=1)

        departures = Departure.search([
            ('start_date', '>=', month_start),
            ('start_date', '<=', month_end),
        ], order='start_date asc')

        calendar_data = {}
        for dep in departures:
            day_key = dep.start_date.day
            fill = round(dep.booked_seats * 100.0 / dep.seats, 0) if dep.seats else 0
            days_to_go = (dep.start_date - today).days

            if dep.booked_seats == 0 and dep.state == 'published' and days_to_go >= 0:
                status = 'zero'
            elif fill >= 80:
                status = 'tight'
            elif fill >= 50:
                status = 'normal'
            elif dep.state == 'ended':
                status = 'ended'
            elif dep.state != 'published':
                status = 'draft'
            else:
                status = 'low'

            if day_key not in calendar_data:
                calendar_data[day_key] = []
            calendar_data[day_key].append({
                'dep': dep,
                'fill_rate': fill,
                'status': status,
                'days_to_go': days_to_go,
            })

        zero_deps = Departure.search([
            ('state', '=', 'published'),
            ('start_date', '>=', today),
            ('start_date', '<=', today + datetime.timedelta(days=15)),
            ('booked_seats', '=', 0),
        ], order='start_date asc')

        urgent_deps = Departure.search([
            ('state', '=', 'published'),
            ('start_date', '>=', today),
            ('start_date', '<=', today + datetime.timedelta(days=7)),
            ('remain_seats', '>', 0),
        ], order='start_date asc')
        urgent_list = []
        for dep in urgent_deps:
            fill = round(dep.booked_seats * 100.0 / dep.seats, 0) if dep.seats else 0
            if fill < 30:
                urgent_list.append({
                    'dep': dep,
                    'fill_rate': fill,
                    'days_to_go': (dep.start_date - today).days,
                })

        zero_data = []
        for dep in zero_deps:
            zero_data.append({
                'dep': dep,
                'days_to_go': (dep.start_date - today).days,
            })

        prev_month = (view_date - datetime.timedelta(days=1)).strftime('%Y-%m')
        next_month = (view_date + datetime.timedelta(days=32)).replace(day=1).strftime('%Y-%m')

        values = {
            'view_date': view_date,
            'month_start': month_start,
            'month_end': month_end,
            'calendar_data': calendar_data,
            'zero_list': zero_data,
            'urgent_list': urgent_list,
            'zero_count': len(zero_deps),
            'urgent_count': len(urgent_list),
            'prev_month': prev_month,
            'next_month': next_month,
            'today': today,
            'month_name': view_date.strftime('%Y年%m月'),
        }
        values.update(self._get_pm_context())
        return request.render('tour_pm_portal.portal_pm_war_room', values)

    # ------------------------------------------------------------------
    # /my/pm/lines/<int:line_id> — 线路详情
    # ------------------------------------------------------------------
    @http.route(['/my/pm/lines/<int:line_id>'], type='http', auth='user', website=True)
    def pm_line_detail(self, line_id, **kw):
        if not self._is_pm_user():
            return request.render('tour_pm_portal.portal_pm_no_access')

        env = request.env
        line = env['tour.line'].sudo().browse(line_id)
        if not line.exists():
            return request.redirect('/my/pm')

        Departure = env['tour.departure'].sudo()
        Plan = env['tour.plan'].sudo()

        departures = Departure.search(
            [('line_id', '=', line.id)],
            order='start_date desc',
        )

        plans = Plan.search(
            [('line_id', '=', line.id), ('state', 'not in', ['draft', 'void'])],
        )
        total_plans = len(plans)
        total_guests = sum(p.guest_count or 0 for p in plans)
        total_revenue = sum(p.in_com_quo_sum or 0 for p in plans)

        cancelled = Plan.search_count([
            ('line_id', '=', line.id),
            ('state', '=', 'void'),
        ])
        cancel_rate = round(cancelled * 100.0 / total_plans, 1) if total_plans else 0

        today = fields.Date.today()
        month_start_12 = (today - datetime.timedelta(days=365)).replace(day=1)
        # 20 起 read_group 换成 (domain, groupby, aggregates) 且返回元组列表。
        # 顺带修一处 19 的死代码：groupby 写成 `'month:begin_date'`（正确是
        # `'begin_date:month'`），于是 `item.get('begin_date:month')` 恒缺失 →
        # 现网这条月度趋势的月份列一直是空串（模板只画 guests/revenue 才没被发现）。
        monthly_data = Plan._read_group(
            [('line_id', '=', line.id), ('begin_date', '>=', month_start_12),
             ('state', 'not in', ['draft', 'void'])],
            ['begin_date:month'],
            ['guest_count:sum', 'in_com_quo_sum:sum'],
            order='begin_date:month asc',
        )
        monthly_trend = []
        for month, guests, revenue in monthly_data:
            monthly_trend.append({
                'month': str(month)[:7] if month else '',
                'guests': guests or 0,
                'revenue': revenue or 0,
            })

        dep_data = []
        for dep in departures:
            fill = round(dep.booked_seats * 100.0 / dep.seats, 0) if dep.seats else 0
            dep_data.append({
                'dep': dep,
                'fill_rate': fill,
            })

        values = {
            'line': line,
            'departures': dep_data,
            'total_plans': total_plans,
            'total_guests': total_guests,
            'total_revenue': total_revenue,
            'cancel_rate': cancel_rate,
            'monthly_trend': monthly_trend,
        }
        values.update(self._get_pm_context())
        return request.render('tour_pm_portal.portal_pm_line_detail', values)

    # ------------------------------------------------------------------
    # /my/pm/departure/<int:dep_id>/action — 班期操作
    # ------------------------------------------------------------------
    @http.route('/my/pm/departure/<int:dep_id>/action', type='jsonrpc', auth='user', website=True)
    def pm_departure_action(self, dep_id, action, **kw):
        """班期操作：adjust_seats / cancel / notify。"""
        if not self._is_pm_user():
            return {'error': _('无权限')}

        env = request.env
        dep = env['tour.departure'].sudo().browse(dep_id)
        if not dep.exists():
            return {'error': _('班期不存在')}

        if action == 'adjust_seats':
            new_seats = kw.get('new_seats')
            if new_seats and new_seats.isdigit():
                dep.write({'seats': int(new_seats)})
                return {'success': True, 'message': _('已调整位数为 %s') % new_seats}
            return {'error': _('请提供有效的位数')}

        elif action == 'cancel':
            dep.write({'state': 'ended'})
            return {'success': True, 'message': _('班期已取消')}

        elif action == 'notify':
            return {'success': True, 'message': _('通知已发送（功能开发中）')}

        return {'error': _('未知操作')}
