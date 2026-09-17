# -*- coding: utf-8 -*-
from collections import OrderedDict
from datetime import date, timedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PortalCMO(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if not self._is_cmo_user():
            return values

        if 'lead_count' in counters:
            values['lead_count'] = request.env['crm.lead'].search_count(
                self._get_lead_domain())
        return values

    def _is_cmo_user(self):
        """检查当前用户是否为 CMO 角色"""
        cmo_group = request.env.ref(
            'tour_cmo_portal.group_cmo_portal', raise_if_not_found=False)
        if not cmo_group:
            return False
        return cmo_group in request.env.user.group_ids

    # === 域定义 ===

    def _get_lead_domain(self):
        """所有活跃线索"""
        return [('active', '=', True)]

    def _get_plan_domain(self):
        """有效团队订单（排除取消和作废）"""
        return [('state', 'not in', ['cancelled', 'void'])]

    def _get_current_month_domain(self, model, date_field='create_date'):
        """当月数据域"""
        today = date.today()
        first_day = today.replace(day=1)
        return [
            (date_field, '>=', fields.Date.to_string(first_day)),
            (date_field, '<=', fields.Date.to_string(today)),
        ]

    # === CMO 门户首页（仪表盘） ===

    @http.route('/my/cmo', type='http', auth='user', website=True)
    def portal_cmo_home(self, **kw):
        if not self._is_cmo_user():
            return request.render('tour_cmo_portal.portal_cmo_no_access')

        Lead = request.env['crm.lead'].sudo()
        Plan = request.env['tour.plan'].sudo()

        # --- 统计卡片 ---
        # 1) 本月营收（已确认以上订单的收入报价合计）
        today = date.today()
        first_day = today.replace(day=1)
        revenue_domain = [
            ('state', 'not in', ['cancelled', 'void', 'draft']),
            ('begin_date', '>=', fields.Date.to_string(first_day)),
        ]
        revenue_data = Plan.read_group(
            revenue_domain,
            ['in_com_quo_sum'],
            [],
        )
        monthly_revenue = revenue_data[0]['in_com_quo_sum'] if revenue_data else 0.0

        # 2) 新线索数（本月）
        lead_month_domain = self._get_current_month_domain('crm.lead')
        new_lead_count = Lead.search_count(lead_month_domain)

        # 3) 成团数（本月出发的团队）
        plan_month_domain = [
            ('state', 'not in', ['cancelled', 'void', 'draft']),
            ('begin_date', '>=', fields.Date.to_string(first_day)),
        ]
        team_count = Plan.search_count(plan_month_domain)

        # 4) 活跃线索总数
        active_lead_count = Lead.search_count(self._get_lead_domain())

        # --- 渠道分布（按 source_id 分组统计本月线索） ---
        channel_data = Lead.read_group(
            lead_month_domain,
            ['source_id'],
            ['source_id'],
        )
        channel_distribution = []
        for item in channel_data:
            source_name = item['source_id'][1] if item.get('source_id') else _('未设置')
            channel_distribution.append({
                'name': source_name,
                'count': item.get('source_id_count', 0),
            })
        channel_distribution.sort(key=lambda x: x['count'], reverse=True)

        # --- 最近线索 ---
        recent_leads = Lead.search(
            self._get_lead_domain(),
            order='create_date desc', limit=10)

        # --- 热门线路（本月订单按线路分组，取收客前 5） ---
        plan_line_domain = [
            ('state', 'not in', ['cancelled', 'void', 'draft']),
            ('begin_date', '>=', fields.Date.to_string(first_day)),
        ]
        line_data = Plan.read_group(
            plan_line_domain,
            ['line_id', 'guest_count'],
            ['line_id'],
        )
        hot_lines = []
        for item in line_data:
            if item['line_id']:
                hot_lines.append({
                    'line_id': item['line_id'][0],
                    'line_name': item['line_id'][1],
                    'guest_count': item['guest_count'],
                    'plan_count': item['line_id_count'],
                })
        hot_lines.sort(key=lambda x: x['guest_count'], reverse=True)
        hot_lines = hot_lines[:5]

        values = {
            'monthly_revenue': monthly_revenue,
            'new_lead_count': new_lead_count,
            'team_count': team_count,
            'active_lead_count': active_lead_count,
            'channel_distribution': channel_distribution,
            'recent_leads': recent_leads,
            'hot_lines': hot_lines,
            'page_name': 'cmo_home',
        }
        return request.render('tour_cmo_portal.portal_cmo_home', values)

    # === 线索列表 ===

    @http.route(['/my/cmo/leads', '/my/cmo/leads/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_cmo_leads(self, page=1, **kw):
        if not self._is_cmo_user():
            return request.render('tour_cmo_portal.portal_cmo_no_access')

        Lead = request.env['crm.lead'].sudo()
        domain = self._get_lead_domain()

        # 搜索和过滤
        searchbar_sortings = {
            'date': {'label': _('创建日期'), 'order': 'create_date desc'},
            'name': {'label': _('线索名称'), 'order': 'name'},
            'revenue': {'label': _('预期收入'), 'order': 'expected_revenue desc'},
            'stage': {'label': _('阶段'), 'order': 'stage_id'},
        }
        searchbar_filters = {
            'all': {'label': _('全部'), 'domain': []},
            'lead': {'label': _('线索'), 'domain': [('type', '=', 'lead')]},
            'opportunity': {'label': _('商机'), 'domain': [('type', '=', 'opportunity')]},
            'won': {'label': _('已赢单'), 'domain': [('stage_id.is_won_stage', '=', True)]},
            'lost': {'label': _('已输单'), 'domain': [('active', '=', False)]},
        }

        sort_label = kw.get('sortby', 'date')
        sort_order = searchbar_sortings.get(
            sort_label, searchbar_sortings['date'])['order']

        filter_label = kw.get('filterby', 'all')
        extra_domain = searchbar_filters.get(
            filter_label, searchbar_filters['all'])['domain']
        domain = domain + extra_domain

        # 搜索关键词
        search = kw.get('search', '')
        if search:
            domain = domain + [
                '|', '|',
                ('name', 'ilike', search),
                ('contact_name', 'ilike', search),
                ('partner_name', 'ilike', search),
            ]

        leads = Lead.search(domain, order=sort_order)

        # 分页
        pager = portal_pager(
            url='/my/cmo/leads',
            url_args={
                'sortby': sort_label,
                'filterby': filter_label,
                'search': search,
            },
            total=len(leads),
            page=page,
            step=20,
        )
        leads = leads[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'default_url': '/my/cmo/leads',
            'leads': leads,
            'page_name': 'cmo_leads',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': OrderedDict(
                sorted(searchbar_filters.items())),
            'sortby': sort_label,
            'filterby': filter_label,
            'default_sortby': 'date',
            'default_filterby': 'all',
            'search': search,
        }
        return request.render('tour_cmo_portal.portal_cmo_leads', values)

    # === 线索详情 ===

    @http.route('/my/cmo/leads/<int:lead_id>',
                type='http', auth='user', website=True)
    def portal_cmo_lead_detail(self, lead_id, **kw):
        if not self._is_cmo_user():
            return request.render('tour_cmo_portal.portal_cmo_no_access')

        lead = request.env['crm.lead'].sudo().browse(lead_id)
        if not lead.exists():
            raise MissingError(_('此线索不存在'))

        # 关联的团队订单
        related_plans = request.env['tour.plan'].sudo().search(
            [('lead_id', '=', lead.id)], order='begin_date desc')

        values = {
            'lead': lead,
            'related_plans': related_plans,
            'page_name': 'cmo_lead_detail',
        }
        return request.render(
            'tour_cmo_portal.portal_cmo_lead_detail', values)

    # === 渠道分析报表 ===

    @http.route('/my/cmo/reports/channels',
                type='http', auth='user', website=True)
    def portal_cmo_channels(self, **kw):
        if not self._is_cmo_user():
            return request.render('tour_cmo_portal.portal_cmo_no_access')

        Lead = request.env['crm.lead'].sudo()
        Plan = request.env['tour.plan'].sudo()

        # 时间范围
        period = kw.get('period', 'month')
        today = date.today()
        if period == 'quarter':
            start_date = today - timedelta(days=90)
        elif period == 'year':
            start_date = today - timedelta(days=365)
        else:
            start_date = today.replace(day=1)

        date_domain = [
            ('create_date', '>=', fields.Date.to_string(start_date)),
        ]

        # 按来源（渠道）分组统计线索
        channel_lead_data = Lead.read_group(
            date_domain,
            ['source_id'],
            ['source_id'],
        )
        channel_stats = []
        for item in channel_lead_data:
            source_name = item['source_id'][1] if item['source_id'] else _('未设置')
            channel_stats.append({
                'name': source_name,
                'lead_count': item.get('source_id_count', 0),
                'source_id': item['source_id'][0] if item['source_id'] else False,
            })
        channel_stats.sort(key=lambda x: x['lead_count'], reverse=True)
        total_leads = sum(c['lead_count'] for c in channel_stats)

        # 按渠道统计营收（通过订单的 channel_name）
        plan_date_domain = [
            ('state', 'not in', ['cancelled', 'void', 'draft']),
            ('begin_date', '>=', fields.Date.to_string(start_date)),
        ]
        channel_revenue_data = Plan.read_group(
            plan_date_domain,
            ['in_com_quo_sum', 'guest_count'],
            ['channel_name'],
        )
        channel_revenue = []
        for item in channel_revenue_data:
            ch_name = item['channel_name'] or _('未设置')
            channel_revenue.append({
                'name': ch_name,
                'revenue': item['in_com_quo_sum'],
                'guest_count': item['guest_count'],
                'plan_count': item['channel_name_count'],
            })
        channel_revenue.sort(key=lambda x: x['revenue'], reverse=True)
        total_revenue = sum(c['revenue'] for c in channel_revenue)

        values = {
            'channel_stats': channel_stats,
            'channel_revenue': channel_revenue,
            'total_leads': total_leads,
            'total_revenue': total_revenue,
            'period': period,
            'page_name': 'cmo_channels',
        }
        return request.render('tour_cmo_portal.portal_cmo_channels', values)

    # === 线路收客分析报表 ===

    @http.route('/my/cmo/reports/products',
                type='http', auth='user', website=True)
    def portal_cmo_products(self, **kw):
        if not self._is_cmo_user():
            return request.render('tour_cmo_portal.portal_cmo_no_access')

        Plan = request.env['tour.plan'].sudo()

        # 时间范围
        period = kw.get('period', 'month')
        today = date.today()
        if period == 'quarter':
            start_date = today - timedelta(days=90)
        elif period == 'year':
            start_date = today - timedelta(days=365)
        else:
            start_date = today.replace(day=1)

        plan_domain = [
            ('state', 'not in', ['cancelled', 'void', 'draft']),
            ('begin_date', '>=', fields.Date.to_string(start_date)),
        ]

        # 按线路分组统计
        line_data = Plan.read_group(
            plan_domain,
            ['line_id', 'guest_count', 'in_com_quo_sum'],
            ['line_id'],
        )
        line_stats = []
        for item in line_data:
            if item['line_id']:
                line_stats.append({
                    'line_id': item['line_id'][0],
                    'line_name': item['line_id'][1],
                    'plan_count': item['line_id_count'],
                    'guest_count': item['guest_count'],
                    'revenue': item['in_com_quo_sum'],
                })
        line_stats.sort(key=lambda x: x['guest_count'], reverse=True)

        total_guests = sum(l['guest_count'] for l in line_stats)
        total_revenue = sum(l['revenue'] for l in line_stats)

        values = {
            'line_stats': line_stats,
            'total_guests': total_guests,
            'total_revenue': total_revenue,
            'period': period,
            'page_name': 'cmo_products',
        }
        return request.render('tour_cmo_portal.portal_cmo_products', values)

    # === 客户分析报表 ===

    @http.route('/my/cmo/reports/customers',
                type='http', auth='user', website=True)
    def portal_cmo_customers(self, **kw):
        if not self._is_cmo_user():
            return request.render('tour_cmo_portal.portal_cmo_no_access')

        Plan = request.env['tour.plan'].sudo()
        Lead = request.env['crm.lead'].sudo()

        # 时间范围
        period = kw.get('period', 'month')
        today = date.today()
        if period == 'quarter':
            start_date = today - timedelta(days=90)
        elif period == 'year':
            start_date = today - timedelta(days=365)
        else:
            start_date = today.replace(day=1)

        # --- 客户地域分析（按订单省份分组） ---
        plan_domain = [
            ('state', 'not in', ['cancelled', 'void', 'draft']),
            ('begin_date', '>=', fields.Date.to_string(start_date)),
        ]
        province_data = Plan.read_group(
            plan_domain,
            ['province', 'guest_count', 'in_com_quo_sum'],
            ['province'],
        )
        province_stats = []
        for item in province_data:
            prov = item['province'] or _('未知')
            province_stats.append({
                'name': prov,
                'plan_count': item['province_count'],
                'guest_count': item['guest_count'],
                'revenue': item['in_com_quo_sum'],
            })
        province_stats.sort(key=lambda x: x['guest_count'], reverse=True)

        # --- 客户排行（按客户档案汇总） ---
        partner_data = Plan.read_group(
            plan_domain,
            ['supplier_id', 'guest_count', 'in_com_quo_sum'],
            ['supplier_id'],
        )
        partner_stats = []
        for item in partner_data:
            if item['supplier_id']:
                partner_stats.append({
                    'partner_id': item['supplier_id'][0],
                    'partner_name': item['supplier_id'][1],
                    'plan_count': item['supplier_id_count'],
                    'guest_count': item['guest_count'],
                    'revenue': item['in_com_quo_sum'],
                })
        partner_stats.sort(key=lambda x: x['revenue'], reverse=True)
        partner_stats = partner_stats[:20]

        # --- 线索来源地域（按 state_id 分组） ---
        lead_date_domain = [
            ('create_date', '>=', fields.Date.to_string(start_date)),
        ]
        state_data = Lead.read_group(
            lead_date_domain,
            ['state_id'],
            ['state_id'],
        )
        state_stats = []
        for item in state_data:
            state_name = item['state_id'][1] if item['state_id'] else _('未知')
            state_stats.append({
                'name': state_name,
                'count': item.get('state_id_count', 0),
            })
        state_stats.sort(key=lambda x: x['count'], reverse=True)

        total_guests = sum(p['guest_count'] for p in province_stats)
        total_revenue = sum(p['revenue'] for p in province_stats)

        values = {
            'province_stats': province_stats,
            'partner_stats': partner_stats,
            'state_stats': state_stats,
            'total_guests': total_guests,
            'total_revenue': total_revenue,
            'period': period,
            'page_name': 'cmo_customers',
        }
        return request.render('tour_cmo_portal.portal_cmo_customers', values)
