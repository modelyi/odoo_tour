# -*- coding: utf-8 -*-
from collections import OrderedDict
from datetime import date, timedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PortalCOO(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if not self._is_coo_user():
            return values

        if 'coo_pending_dispatch_count' in counters:
            values['coo_pending_dispatch_count'] = request.env['project.task'].search_count(
                self._get_dispatch_domain())
        if 'coo_active_plan_count' in counters:
            values['coo_active_plan_count'] = request.env['tour.plan'].search_count(
                self._get_active_plan_domain())
        if 'coo_pending_approval_count' in counters:
            values['coo_pending_approval_count'] = request.env['tour.plan'].search_count(
                self._get_approval_domain())
        return values

    def _is_coo_user(self):
        """检查当前用户是否为 COO 角色"""
        coo_group = request.env.ref(
            'tour_coo_portal.group_coo_portal', raise_if_not_found=False)
        if not coo_group:
            return False
        return coo_group in request.env.user.group_ids

    # === 域定义 ===

    def _get_active_plan_domain(self):
        """活跃团队（已确认/计调中/出行中）"""
        return [('state', 'in', ['confirmed', 'operating', 'in_progress'])]

    def _get_dispatch_domain(self):
        """待调度任务"""
        return [('state', '=', '01_in_progress')]

    def _get_approval_domain(self):
        """待审批团队"""
        return [('operation_audit_state', '=', 'pending')]

    def _get_plan_pipeline_domain(self):
        """订单管线（排除草稿和作废）"""
        return [('state', 'not in', ['draft', 'cancelled', 'void'])]

    # === COO 门户首页（仪表盘） ===

    @http.route('/my/coo', type='http', auth='user', website=True)
    def portal_coo_home(self, **kw):
        if not self._is_coo_user():
            return request.render('tour_coo_portal.portal_coo_no_access')

        Plan = request.env['tour.plan'].sudo()
        Task = request.env['project.task'].sudo()

        today = date.today()
        today_str = fields.Date.to_string(today)
        week_later_str = fields.Date.to_string(today + timedelta(days=7))

        # --- 统计卡片 ---
        active_plan_count = Plan.search_count(self._get_active_plan_domain())
        pending_dispatch_count = Task.search_count(self._get_dispatch_domain())

        upcoming_7d_domain = [
            ('begin_date', '>=', today_str),
            ('begin_date', '<=', week_later_str),
            ('state', 'in', ['confirmed', 'operating']),
        ]
        upcoming_7d_count = Plan.search_count(upcoming_7d_domain)

        pending_approval_count = Plan.search_count(self._get_approval_domain())

        # --- 即将出发的团队 ---
        upcoming_domain = [
            ('begin_date', '>=', today_str),
            ('state', 'in', ['confirmed', 'operating']),
        ]
        upcoming_departures = Plan.search(
            upcoming_domain, order='begin_date asc', limit=10)

        # --- 最近待审批 ---
        pending_approvals = Plan.search(
            self._get_approval_domain(),
            order='id desc', limit=10)

        # --- 资源类型分布（按 project.task 的 resource_type 分组） ---
        resource_type_labels = {
            'guide': '派导',
            'vehicle': '派车',
            'hotel': '订房',
            'meal': '订餐',
            'scenic': '门票',
            'insurance': '保险',
            'ditch': '地接',
        }
        task_in_progress = Task.search(self._get_dispatch_domain())
        resource_type_counts = {}
        for rt_key, rt_label in resource_type_labels.items():
            count = len(task_in_progress.filtered(
                lambda t: t.resource_type == rt_key))
            resource_type_counts[rt_key] = {
                'label': rt_label,
                'count': count,
            }
        total_tasks = len(task_in_progress)
        for rt_key in resource_type_counts:
            c = resource_type_counts[rt_key]['count']
            resource_type_counts[rt_key]['percentage'] = (
                '%.1f' % (c / total_tasks * 100) if total_tasks else '0.0')

        # --- 团队状态分布 ---
        state_labels = {
            'pending': '待确认',
            'confirmed': '已确认',
            'operating': '计调中',
            'in_progress': '出行中',
            'completed': '已完成',
            'archived': '已归档',
            'refunded': '已退款',
        }
        plan_exclude_domain = [('state', 'not in', ['draft', 'cancelled', 'void'])]
        all_plans = Plan.search(plan_exclude_domain)
        tour_state_distribution = {}
        for st_key, st_label in state_labels.items():
            count = len(all_plans.filtered(lambda p: p.state == st_key))
            if count > 0:
                tour_state_distribution[st_key] = {
                    'label': st_label,
                    'count': count,
                }
        total_plans = len(all_plans)
        for st_key in tour_state_distribution:
            c = tour_state_distribution[st_key]['count']
            tour_state_distribution[st_key]['percentage'] = (
                '%.1f' % (c / total_plans * 100) if total_plans else '0.0')

        values = {
            'active_plan_count': active_plan_count,
            'pending_dispatch_count': pending_dispatch_count,
            'upcoming_7d_count': upcoming_7d_count,
            'pending_approval_count': pending_approval_count,
            'upcoming_departures': upcoming_departures,
            'pending_approvals': pending_approvals,
            'resource_type_counts': resource_type_counts,
            'tour_state_distribution': tour_state_distribution,
            'page_name': 'coo_home',
        }
        return request.render('tour_coo_portal.portal_coo_home', values)

    # === 订单管线 ===

    @http.route(['/my/coo/orders', '/my/coo/orders/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_coo_orders(self, page=1, **kw):
        if not self._is_coo_user():
            return request.render('tour_coo_portal.portal_coo_no_access')

        Plan = request.env['tour.plan'].sudo()
        domain = self._get_plan_pipeline_domain()

        # 排序
        searchbar_sortings = {
            'date': {'label': _('出发日期'), 'order': 'begin_date desc'},
            'amount': {'label': _('收入报价'), 'order': 'in_com_quo_sum desc'},
            'state': {'label': _('状态'), 'order': 'state'},
            'guest_count': {'label': _('人数'), 'order': 'guest_count desc'},
        }
        # 过滤
        searchbar_filters = {
            'all': {'label': _('全部'), 'domain': []},
            'confirmed': {'label': _('已确认'), 'domain': [('state', '=', 'confirmed')]},
            'operating': {'label': _('计调中'), 'domain': [('state', '=', 'operating')]},
            'in_progress': {'label': _('出行中'), 'domain': [('state', '=', 'in_progress')]},
            'completed': {'label': _('已完成'), 'domain': [('state', '=', 'completed')]},
        }

        sort_label = kw.get('sortby', 'date')
        sort_order = searchbar_sortings.get(
            sort_label, searchbar_sortings['date'])['order']

        filter_label = kw.get('filterby', 'all')
        extra_domain = searchbar_filters.get(
            filter_label, searchbar_filters['all'])['domain']
        domain = domain + extra_domain

        # 搜索
        search = kw.get('search', '')
        if search:
            domain = domain + [
                '|', '|',
                ('plan_code', 'ilike', search),
                ('plan_name', 'ilike', search),
                ('supplier_id.name', 'ilike', search),
            ]

        plans = Plan.search(domain, order=sort_order)

        # 分页
        pager = portal_pager(
            url='/my/coo/orders',
            url_args={
                'sortby': sort_label,
                'filterby': filter_label,
                'search': search,
            },
            total=len(plans),
            page=page,
            step=20,
        )
        plans = plans[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'default_url': '/my/coo/orders',
            'plans': plans,
            'page_name': 'coo_orders',
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
        return request.render('tour_coo_portal.portal_coo_orders', values)

    # === 资源调度看板 ===

    @http.route(['/my/coo/dispatches', '/my/coo/dispatches/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_coo_dispatches(self, page=1, **kw):
        if not self._is_coo_user():
            return request.render('tour_coo_portal.portal_coo_no_access')

        Task = request.env['project.task'].sudo()
        domain = self._get_dispatch_domain()

        # 排序
        searchbar_sortings = {
            'date': {'label': _('开始时间'), 'order': 'date_start desc'},
            'resource_type': {'label': _('资源类型'), 'order': 'resource_type'},
            'plan': {'label': _('团号'), 'order': 'plan_code'},
        }
        # 过滤
        searchbar_filters = {
            'all': {'label': _('全部'), 'domain': []},
            'guide': {'label': _('派导'), 'domain': [('resource_type', '=', 'guide')]},
            'vehicle': {'label': _('派车'), 'domain': [('resource_type', '=', 'vehicle')]},
            'hotel': {'label': _('订房'), 'domain': [('resource_type', '=', 'hotel')]},
            'meal': {'label': _('订餐'), 'domain': [('resource_type', '=', 'meal')]},
            'scenic': {'label': _('门票'), 'domain': [('resource_type', '=', 'scenic')]},
            'insurance': {'label': _('保险'), 'domain': [('resource_type', '=', 'insurance')]},
            'ditch': {'label': _('地接'), 'domain': [('resource_type', '=', 'ditch')]},
        }

        sort_label = kw.get('sortby', 'date')
        sort_order = searchbar_sortings.get(
            sort_label, searchbar_sortings['date'])['order']

        filter_label = kw.get('filterby', 'all')
        extra_domain = searchbar_filters.get(
            filter_label, searchbar_filters['all'])['domain']
        domain = domain + extra_domain

        tasks = Task.search(domain, order=sort_order)

        # 各资源类型计数（顶部卡片用）
        all_dispatch_tasks = Task.search(self._get_dispatch_domain())
        resource_type_counts = {}
        type_icons = {
            'guide': 'fa-user',
            'vehicle': 'fa-bus',
            'hotel': 'fa-hotel',
            'meal': 'fa-cutlery',
            'scenic': 'fa-ticket',
            'insurance': 'fa-shield',
            'ditch': 'fa-globe',
        }
        type_labels = {
            'guide': '派导',
            'vehicle': '派车',
            'hotel': '订房',
            'meal': '订餐',
            'scenic': '门票',
            'insurance': '保险',
            'ditch': '地接',
        }
        for rt_key in type_labels:
            resource_type_counts[rt_key] = {
                'label': type_labels[rt_key],
                'icon': type_icons[rt_key],
                'count': len(all_dispatch_tasks.filtered(
                    lambda t: t.resource_type == rt_key)),
            }

        # 分页
        pager = portal_pager(
            url='/my/coo/dispatches',
            url_args={
                'sortby': sort_label,
                'filterby': filter_label,
            },
            total=len(tasks),
            page=page,
            step=20,
        )
        tasks = tasks[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'default_url': '/my/coo/dispatches',
            'tasks': tasks,
            'resource_type_counts': resource_type_counts,
            'page_name': 'coo_dispatches',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': OrderedDict(
                sorted(searchbar_filters.items())),
            'sortby': sort_label,
            'filterby': filter_label,
            'default_sortby': 'date',
            'default_filterby': 'all',
        }
        return request.render('tour_coo_portal.portal_coo_dispatches', values)

    # === 供应商总览 ===

    @http.route(['/my/coo/suppliers', '/my/coo/suppliers/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_coo_suppliers(self, page=1, **kw):
        if not self._is_coo_user():
            return request.render('tour_coo_portal.portal_coo_no_access')

        Supplier = request.env['tour.supplier'].sudo()

        # --- 类型分布 ---
        sup_type_labels = {
            'customer': '客户',
            'ditch': '地接社',
            'hotel': '酒店',
            'meal': '餐厅',
            'vehicle_comp': '车队',
            'ticket': '票务',
            'scenic': '景区',
            'shop': '购物店',
            'insurance': '保险',
            'self_fee': '自费',
        }
        all_suppliers = Supplier.search([])
        supplier_type_distribution = []
        for st_key, st_label in sup_type_labels.items():
            count = len(all_suppliers.filtered(
                lambda s: s.sup_type == st_key))
            if count > 0:
                supplier_type_distribution.append({
                    'label': st_label,
                    'count': count,
                })
        total_suppliers = len(all_suppliers)
        for item in supplier_type_distribution:
            item['percentage'] = (
                '%.1f' % (item['count'] / total_suppliers * 100)
                if total_suppliers else '0.0')

        # --- 等级分布 ---
        level_labels = {
            'a': 'A 级',
            'b': 'B 级',
            'c': 'C 级',
            'd': 'D 级',
        }
        supplier_level_distribution = []
        for lv_key, lv_label in level_labels.items():
            count = len(all_suppliers.filtered(
                lambda s: s.level_id == lv_key))
            if count > 0:
                supplier_level_distribution.append({
                    'label': lv_label,
                    'count': count,
                })

        # --- 即将到期合同（30 天内） ---
        today = date.today()
        today_str = fields.Date.to_string(today)
        expiry_str = fields.Date.to_string(today + timedelta(days=30))
        expiring_domain = [
            ('contract_end_date', '>=', today_str),
            ('contract_end_date', '<=', expiry_str),
        ]
        expiring_contracts = Supplier.search(
            expiring_domain, order='contract_end_date asc')

        # --- 全部供应商（分页） ---
        search = kw.get('search', '')
        supplier_domain = []
        if search:
            supplier_domain = [
                '|', '|',
                ('name', 'ilike', search),
                ('contract_no', 'ilike', search),
                ('manager', 'ilike', search),
            ]
        suppliers = Supplier.search(supplier_domain, order='name')

        pager = portal_pager(
            url='/my/coo/suppliers',
            url_args={'search': search},
            total=len(suppliers),
            page=page,
            step=20,
        )
        suppliers = suppliers[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'default_url': '/my/coo/suppliers',
            'suppliers': suppliers,
            'supplier_type_distribution': supplier_type_distribution,
            'supplier_level_distribution': supplier_level_distribution,
            'expiring_contracts': expiring_contracts,
            'page_name': 'coo_suppliers',
            'pager': pager,
            'search': search,
        }
        return request.render('tour_coo_portal.portal_coo_suppliers', values)

    # === 运营审批 ===

    @http.route(['/my/coo/approvals', '/my/coo/approvals/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_coo_approvals(self, page=1, **kw):
        if not self._is_coo_user():
            return request.render('tour_coo_portal.portal_coo_no_access')

        Plan = request.env['tour.plan'].sudo()
        domain = self._get_approval_domain()

        plans = Plan.search(domain, order='id desc')

        pager = portal_pager(
            url='/my/coo/approvals',
            total=len(plans),
            page=page,
            step=20,
        )
        plans = plans[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'plans': plans,
            'page_name': 'coo_approvals',
            'pager': pager,
        }
        return request.render('tour_coo_portal.portal_coo_approvals', values)

    @http.route('/my/coo/approvals/<int:plan_id>/approve',
                type='http', auth='user', website=True, methods=['POST'])
    def portal_coo_approval_action(self, plan_id, **kw):
        if not self._is_coo_user():
            return request.render('tour_coo_portal.portal_coo_no_access')

        plan = request.env['tour.plan'].sudo().browse(plan_id)
        if not plan.exists():
            raise MissingError(_('此团队记录不存在'))

        action = kw.get('action', '')
        if action == 'approve':
            plan.write({
                'operation_audit_state': 'approved',
                'operation_audit_uid': request.env.user.id,
                'operation_audit_date': fields.Datetime.now(),
            })
        elif action == 'reject':
            plan.write({
                'operation_audit_state': 'rejected',
                'operation_audit_uid': request.env.user.id,
                'operation_audit_date': fields.Datetime.now(),
            })

        return request.redirect('/my/coo/approvals')
