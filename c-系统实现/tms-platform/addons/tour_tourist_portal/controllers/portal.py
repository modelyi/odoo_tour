# -*- coding: utf-8 -*-
"""游客门户控制器。

路由：
- /my/tourist              仪表盘（4 KPI + 最近订单）
- /my/tourist/orders       订单列表（搜索/过滤/排序/分页）
- /my/tourist/orders/<id>  订单详情（客人/金额/付款摘要）
- /my/tourist/payments     付款记录
- /my/tourist/trips        即将出行
- /my/tourist/invoices     发票列表
- /website/signup          注册（GET 表单 / POST 创建用户）

数据隔离：所有查询均按 partner_id = request.env.user.partner_id.id 过滤。
"""
from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PortalTourist(CustomerPortal):

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _is_tourist_user(self):
        """检查当前用户是否为游客门户角色"""
        group = request.env.ref(
            'tour_tourist_portal.group_tourist_portal', raise_if_not_found=False)
        if not group:
            return False
        return group in request.env.user.group_ids

    def _get_partner_id(self):
        """当前登录用户的 partner_id"""
        return request.env.user.partner_id.id

    def _get_reg_domain(self):
        """报名记录基础域"""
        return [('partner_id', '=', self._get_partner_id())]

    def _get_plan_ids_from_regs(self, regs):
        """从报名记录提取关联的 plan_ids"""
        return regs.mapped('plan_id').ids

    @staticmethod
    def _state_label(record, field='state'):
        """selection 字段的人类可读标签"""
        return dict(record._fields[field].selection).get(
            record[field] or '', '')

    @staticmethod
    def _state_badge_class(state):
        """根据状态返回 Bootstrap badge class"""
        mapping = {
            'draft': 'bg-secondary',
            'confirmed': 'bg-success',
            'cancelled': 'bg-danger',
            'pending': 'bg-warning',
            'operating': 'bg-info',
            'in_progress': 'bg-primary',
            'completed': 'bg-success',
            'archived': 'bg-secondary',
        }
        return mapping.get(state, 'bg-secondary')

    # ------------------------------------------------------------------
    # /my/tourist — 仪表盘
    # ------------------------------------------------------------------

    @http.route('/my/tourist', type='http', auth='user', website=True)
    def portal_tourist_home(self, **kw):
        if not self._is_tourist_user():
            return request.render('tour_tourist_portal.portal_tourist_no_access')

        partner_id = self._get_partner_id()
        Reg = request.env['tour.plan.reg'].sudo()

        # 全部报名
        all_regs = Reg.search(self._get_reg_domain(), order='id desc')

        # KPI 1：总订单数
        total_orders = len(all_regs)

        # KPI 2：待付金额（sum_un_pay 合计）
        pending_amount = sum(all_regs.mapped('sum_un_pay'))

        # KPI 3：即将出行（plan state in confirmed/operating/in_progress）
        upcoming_regs = all_regs.filtered(
            lambda r: r.plan_id.state in (
                'confirmed', 'operating', 'in_progress'))
        upcoming_trips = len(upcoming_regs)

        # KPI 4：已完成
        completed_count = len(all_regs.filtered(
            lambda r: r.plan_id.state in ('completed', 'archived')))

        # 最近订单（5 条）
        recent_regs = all_regs[:5]

        # 付款提醒：有待付金额的订单
        reminder_regs = all_regs.filtered(lambda r: r.sum_un_pay > 0)[:3]

        values = {
            'total_orders': total_orders,
            'pending_amount': pending_amount,
            'upcoming_trips': upcoming_trips,
            'completed_count': completed_count,
            'recent_regs': recent_regs,
            'reminder_regs': reminder_regs,
            'page_name': 'tourist_home',
        }
        return request.render('tour_tourist_portal.portal_tourist_home', values)

    # ------------------------------------------------------------------
    # /my/tourist/orders — 订单列表
    # ------------------------------------------------------------------

    @http.route(['/my/tourist/orders', '/my/tourist/orders/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_tourist_orders(self, page=1, **kw):
        if not self._is_tourist_user():
            return request.render('tour_tourist_portal.portal_tourist_no_access')

        Reg = request.env['tour.plan.reg'].sudo()
        domain = self._get_reg_domain()

        # 过滤
        filterby = kw.get('filterby', 'all')
        if filterby == 'active':
            domain.append(('state', '!=', 'cancelled'))
        elif filterby == 'cancelled':
            domain.append(('state', '=', 'cancelled'))

        # 搜索
        search = (kw.get('search') or '').strip()
        if search:
            domain += ['|',
                       ('reg_code', 'ilike', search),
                       ('supplier_name', 'ilike', search)]

        # 排序
        searchbar_sortings = {
            'date': {'label': _('下单日期'), 'order': 'order_date desc, id desc'},
            'code': {'label': _('报名单号'), 'order': 'reg_code'},
            'amount': {'label': _('金额'), 'order': 'in_com_quo_sum desc'},
        }
        sortby = kw.get('sortby', 'date')
        sort_order = searchbar_sortings.get(
            sortby, searchbar_sortings['date'])['order']

        regs = Reg.search(domain, order=sort_order)

        # 分页
        pager = portal_pager(
            url='/my/tourist/orders',
            url_args={'search': search, 'sortby': sortby,
                      'filterby': filterby},
            total=len(regs),
            page=page,
            step=20,
        )
        regs = regs[pager['offset']:pager['offset'] + 20]

        values = {
            'regs': regs,
            'page_name': 'tourist_orders',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'default_sortby': 'date',
            'filterby': filterby,
            'search': search,
        }
        return request.render('tour_tourist_portal.portal_tourist_orders', values)

    # ------------------------------------------------------------------
    # /my/tourist/orders/<reg_id> — 订单详情
    # ------------------------------------------------------------------

    @http.route('/my/tourist/orders/<int:reg_id>',
                type='http', auth='user', website=True)
    def portal_tourist_order_detail(self, reg_id, **kw):
        if not self._is_tourist_user():
            return request.render('tour_tourist_portal.portal_tourist_no_access')

        reg = request.env['tour.plan.reg'].sudo().browse(reg_id)
        if not reg.exists():
            raise MissingError(_('此订单不存在'))
        if reg.partner_id.id != self._get_partner_id():
            raise AccessError(_('无权查看此订单'))

        # 付款记录（通过 plan 关联）
        claims = request.env['tour.payment.claim'].sudo().search([
            ('plan_id', '=', reg.plan_id.id),
        ], order='pay_date desc') if reg.plan_id else []

        values = {
            'reg': reg,
            'claims': claims,
            'page_name': 'tourist_orders',
        }
        return request.render(
            'tour_tourist_portal.portal_tourist_order_detail', values)

    # ------------------------------------------------------------------
    # /my/tourist/payments — 付款记录
    # ------------------------------------------------------------------

    @http.route(['/my/tourist/payments', '/my/tourist/payments/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_tourist_payments(self, page=1, **kw):
        if not self._is_tourist_user():
            return request.render('tour_tourist_portal.portal_tourist_no_access')

        partner_id = self._get_partner_id()
        Reg = request.env['tour.plan.reg'].sudo()
        regs = Reg.search([('partner_id', '=', partner_id)])
        plan_ids = self._get_plan_ids_from_regs(regs)

        Claim = request.env['tour.payment.claim'].sudo()
        if plan_ids:
            claims = Claim.search(
                [('plan_id', 'in', plan_ids)],
                order='pay_date desc')
        else:
            claims = Claim.browse()

        # 汇总
        total_paid = sum(claims.mapped('pay_money'))

        pager = portal_pager(
            url='/my/tourist/payments',
            total=len(claims),
            page=page,
            step=20,
        )
        claims_page = claims[pager['offset']:pager['offset'] + 20]

        values = {
            'claims': claims_page,
            'total_paid': total_paid,
            'page_name': 'tourist_payments',
            'pager': pager,
        }
        return request.render(
            'tour_tourist_portal.portal_tourist_payments', values)

    # ------------------------------------------------------------------
    # /my/tourist/trips — 即将出行
    # ------------------------------------------------------------------

    @http.route('/my/tourist/trips', type='http', auth='user', website=True)
    def portal_tourist_trips(self, **kw):
        if not self._is_tourist_user():
            return request.render('tour_tourist_portal.portal_tourist_no_access')

        partner_id = self._get_partner_id()
        Reg = request.env['tour.plan.reg'].sudo()
        regs = Reg.search([('partner_id', '=', partner_id)])

        # 筛选即将出行：plan state in confirmed/operating/in_progress
        # 且出发日期 >= 今天
        today = fields.Date.today()
        upcoming = regs.filtered(
            lambda r: r.plan_id.state in (
                'confirmed', 'operating', 'in_progress')
            and r.begin_date >= today
        ).sorted('begin_date')

        values = {
            'upcoming': upcoming,
            'page_name': 'tourist_trips',
        }
        return request.render(
            'tour_tourist_portal.portal_tourist_trips', values)

    # ------------------------------------------------------------------
    # /my/tourist/invoices — 发票列表
    # ------------------------------------------------------------------

    @http.route(['/my/tourist/invoices',
                 '/my/tourist/invoices/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_tourist_invoices(self, page=1, **kw):
        if not self._is_tourist_user():
            return request.render('tour_tourist_portal.portal_tourist_no_access')

        partner_id = self._get_partner_id()
        Move = request.env['account.move'].sudo()
        invoices = Move.search([
            ('partner_id', '=', partner_id),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
        ], order='invoice_date desc, id desc')

        pager = portal_pager(
            url='/my/tourist/invoices',
            total=len(invoices),
            page=page,
            step=20,
        )
        invoices_page = invoices[pager['offset']:pager['offset'] + 20]

        values = {
            'invoices': invoices_page,
            'page_name': 'tourist_invoices',
            'pager': pager,
        }
        return request.render(
            'tour_tourist_portal.portal_tourist_invoices', values)

    # ------------------------------------------------------------------
    # /website/signup — 注册
    # ------------------------------------------------------------------

    @http.route('/website/signup', type='http', auth='public',
                website=True, methods=['GET'])
    def signup_form(self, **kw):
        """注册表单页"""
        return request.render('tour_tourist_portal.portal_signup_form', {
            'error': kw.get('error', ''),
            'post': {},
        })

    @http.route('/website/signup', type='http', auth='public',
                website=True, methods=['POST'], csrf=True)
    def signup_submit(self, **post):
        """注册提交：创建 partner + user，分配游客组，自动登录"""
        phone = (post.get('phone') or '').strip()
        name = (post.get('name') or '').strip()
        password = post.get('password') or ''
        confirm = post.get('confirm_password') or ''

        # 校验
        error = ''
        if not phone or len(phone) != 11 or not phone.isdigit():
            error = '请填写正确的 11 位手机号'
        elif not name:
            error = '请填写姓名'
        elif not password or len(password) < 6:
            error = '密码至少 6 位'
        elif password != confirm:
            error = '两次密码不一致'

        if error:
            return request.render(
                'tour_tourist_portal.portal_signup_form', {
                    'error': error,
                    'post': post,
                })

        # 检查手机号是否已注册
        existing = request.env['res.partner'].sudo().search([
            ('mobile', '=', phone),
        ], limit=1)
        if existing and existing.user_ids:
            return request.render(
                'tour_tourist_portal.portal_signup_form', {
                    'error': '该手机号已注册，请直接登录',
                    'post': post,
                })

        # 创建 partner
        partner_vals = {
            'name': name,
            'mobile': phone,
        }
        if existing:
            partner = existing
        else:
            partner = request.env['res.partner'].sudo().create(partner_vals)

        # 创建 user
        tourist_group = request.env.ref(
            'tour_tourist_portal.group_tourist_portal')
        portal_group = request.env.ref('base.group_portal')

        user = request.env['res.users'].sudo().create({
            'name': name,
            'login': phone,
            'password': password,
            'partner_id': partner.id,
            'groups_id': [(6, 0, [portal_group.id, tourist_group.id])],
        })

        # 自动登录
        request.session.authenticate(
            request.env.cr.dbname, phone, password)

        return request.redirect('/my/tourist')
