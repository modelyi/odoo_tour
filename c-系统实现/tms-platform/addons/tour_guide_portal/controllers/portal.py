# -*- coding: utf-8 -*-
from collections import OrderedDict

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PortalGuide(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        guide = self._get_current_guide()
        if not guide:
            return values
        if 'dispatch_count' in counters:
            values['dispatch_count'] = request.env['project.task'].search_count(
                self._get_dispatch_domain(guide))
        if 'commission_count' in counters:
            values['commission_count'] = request.env['tour.commission'].search_count(
                self._get_commission_domain(guide))
        if 'loan_count' in counters:
            values['loan_count'] = request.env['tour.guide.loan'].search_count(
                self._get_loan_domain(guide))
        if 'expense_count' in counters:
            values['expense_count'] = request.env['hr.expense'].search_count(
                self._get_expense_domain(guide))
        return values

    def _get_current_guide(self):
        """获取当前登录用户关联的导游档案。"""
        partner = request.env.user.partner_id
        guide = request.env['tour.guide'].sudo().search([
            ('partner_id', '=', partner.id),
        ], limit=1)
        return guide

    # === 派团 ===

    def _get_dispatch_domain(self, guide):
        return [
            ('resource_type', '=', 'guide'),
            ('guide_id', '=', guide.id),
            ('state', 'not in', ['1_canceled']),
        ]

    @http.route(['/my/guide/dispatches', '/my/guide/dispatches/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_dispatches(self, page=1, sortby=None, filterby=None, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')

        Domain = self._get_dispatch_domain(guide)
        Task = request.env['project.task']

        searchbar_sortings = OrderedDict([
            ('date', {'label': _('开始时间'), 'order': 'date_start desc'}),
            ('name', {'label': _('预订编号'), 'order': 'booking_no desc'}),
        ])
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        tasks = Task.search(Domain, order=order)
        pager_data = portal_pager(
            url='/my/guide/dispatches',
            total=len(tasks),
            page=page,
            step=20,
        )
        tasks = tasks[(page - 1) * 20:page * 20]

        values = {
            'tasks': tasks,
            'guide': guide,
            'page_name': 'dispatches',
            'pager': pager_data,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'default_url': '/my/guide/dispatches',
        }
        return request.render('tour_guide_portal.portal_my_dispatches', values)

    @http.route('/my/guide/dispatches/<int:task_id>',
                type='http', auth='user', website=True)
    def portal_dispatch_detail(self, task_id, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')
        task = request.env['project.task'].sudo().browse(task_id)
        if task.guide_id.id != guide.id:
            raise AccessError(_('无权查看此派团记录'))
        values = {
            'task': task,
            'guide': guide,
            'page_name': 'dispatch_detail',
        }
        return request.render('tour_guide_portal.portal_dispatch_detail', values)

    # === 佣金 ===

    def _get_commission_domain(self, guide):
        return [('guide_id', '=', guide.id)]

    @http.route(['/my/guide/commissions', '/my/guide/commissions/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_commissions(self, page=1, sortby=None, filterby=None, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')

        Domain = self._get_commission_domain(guide)
        Commission = request.env['tour.commission']

        searchbar_filters = OrderedDict([
            ('all', {'label': _('全部'), 'domain': []}),
            ('draft', {'label': _('待确认'), 'domain': [('state', '=', 'draft')]}),
            ('confirmed', {'label': _('已确认'), 'domain': [('state', '=', 'confirmed')]}),
            ('paid', {'label': _('已发放'), 'domain': [('state', '=', 'paid')]}),
        ])
        if not filterby:
            filterby = 'all'
        domain_ext = searchbar_filters[filterby]['domain']

        commissions = Commission.search(Domain + domain_ext, order='id desc')
        pager_data = portal_pager(
            url='/my/guide/commissions',
            total=len(commissions),
            page=page,
            step=20,
        )
        commissions = commissions[(page - 1) * 20:page * 20]

        values = {
            'commissions': commissions,
            'guide': guide,
            'page_name': 'commissions',
            'pager': pager_data,
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
            'default_url': '/my/guide/commissions',
        }
        return request.render('tour_guide_portal.portal_my_commissions', values)

    @http.route('/my/guide/commissions/<int:commission_id>',
                type='http', auth='user', website=True)
    def portal_commission_detail(self, commission_id, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')
        commission = request.env['tour.commission'].sudo().browse(commission_id)
        if commission.guide_id.id != guide.id:
            raise AccessError(_('无权查看此佣金记录'))
        values = {
            'commission': commission,
            'guide': guide,
            'page_name': 'commission_detail',
        }
        return request.render('tour_guide_portal.portal_commission_detail', values)

    # === 借款 ===

    def _get_loan_domain(self, guide):
        return ['|',
                ('guide_id', '=', guide.id),
                ('employee_id', '=', guide.employee_id.id if guide.employee_id else False)]

    @http.route(['/my/guide/loans', '/my/guide/loans/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_loans(self, page=1, sortby=None, filterby=None, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')

        Domain = self._get_loan_domain(guide)
        Loan = request.env['tour.guide.loan']

        searchbar_filters = OrderedDict([
            ('all', {'label': _('全部'), 'domain': []}),
            ('draft', {'label': _('待审批'), 'domain': [('state', '=', 'draft')]}),
            ('disbursed', {'label': _('已放款'), 'domain': [('state', '=', 'disbursed')]}),
            ('overdue', {'label': _('已超期'), 'domain': [('is_overdue', '=', True)]}),
        ])
        if not filterby:
            filterby = 'all'
        domain_ext = searchbar_filters[filterby]['domain']

        loans = Loan.search(Domain + domain_ext, order='apply_date desc')
        pager_data = portal_pager(
            url='/my/guide/loans',
            total=len(loans),
            page=page,
            step=20,
        )
        loans = loans[(page - 1) * 20:page * 20]

        values = {
            'loans': loans,
            'guide': guide,
            'page_name': 'loans',
            'pager': pager_data,
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
            'default_url': '/my/guide/loans',
        }
        return request.render('tour_guide_portal.portal_my_loans', values)

    @http.route('/my/guide/loans/<int:loan_id>',
                type='http', auth='user', website=True)
    def portal_loan_detail(self, loan_id, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')
        loan = request.env['tour.guide.loan'].sudo().browse(loan_id)
        if loan.guide_id.id != guide.id and loan.employee_id.id != (guide.employee_id.id if guide.employee_id else False):
            raise AccessError(_('无权查看此借款记录'))
        values = {
            'loan': loan,
            'guide': guide,
            'page_name': 'loan_detail',
        }
        return request.render('tour_guide_portal.portal_loan_detail', values)

    # === 报账 ===

    def _get_expense_domain(self, guide):
        return ['|',
                ('x_guide_id', '=', guide.id),
                ('employee_id', '=', guide.employee_id.id if guide.employee_id else False)]

    @http.route(['/my/guide/expenses', '/my/guide/expenses/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_expenses(self, page=1, sortby=None, filterby=None, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')

        Domain = self._get_expense_domain(guide)
        Expense = request.env['hr.expense']

        searchbar_filters = OrderedDict([
            ('all', {'label': _('全部'), 'domain': []}),
            ('draft', {'label': _('草稿'), 'domain': [('state', '=', 'draft')]}),
            ('reported', {'label': _('已提交'), 'domain': [('state', '=', 'reported')]}),
            ('approved', {'label': _('已审批'), 'domain': [('state', '=', 'approved')]}),
        ])
        if not filterby:
            filterby = 'all'
        domain_ext = searchbar_filters[filterby]['domain']

        expenses = Expense.search(Domain + domain_ext, order='date desc')
        pager_data = portal_pager(
            url='/my/guide/expenses',
            total=len(expenses),
            page=page,
            step=20,
        )
        expenses = expenses[(page - 1) * 20:page * 20]

        values = {
            'expenses': expenses,
            'guide': guide,
            'page_name': 'expenses',
            'pager': pager_data,
            'searchbar_filters': searchbar_filters,
            'filterby': filterby,
            'default_url': '/my/guide/expenses',
        }
        return request.render('tour_guide_portal.portal_my_expenses', values)

    @http.route('/my/guide/expenses/<int:expense_id>',
                type='http', auth='user', website=True)
    def portal_expense_detail(self, expense_id, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')
        expense = request.env['hr.expense'].sudo().browse(expense_id)
        if expense.x_guide_id.id != guide.id and expense.employee_id.id != (guide.employee_id.id if guide.employee_id else False):
            raise AccessError(_('无权查看此报账记录'))
        values = {
            'expense': expense,
            'guide': guide,
            'page_name': 'expense_detail',
        }
        return request.render('tour_guide_portal.portal_expense_detail', values)

    @http.route('/my/guide/expenses/new', type='http', auth='user',
                website=True, methods=['GET', 'POST'])
    def portal_expense_new(self, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')

        if request.httprequest.method == 'GET':
            plans = request.env['tour.plan'].sudo().search([
                ('guide_ids', 'in', guide.id),
                ('state', 'not in', ['cancelled', 'void']),
            ], order='begin_date desc', limit=20)
            products = request.env['product.product'].sudo().search([
                ('x_expense_type', '!=', False),
            ], limit=50)
            loans = request.env['tour.guide.loan'].sudo().search([
                ('guide_id', '=', guide.id),
                ('state', '=', 'disbursed'),
            ], order='apply_date desc', limit=10)
            values = {
                'guide': guide,
                'plans': plans,
                'products': products,
                'loans': loans,
                'page_name': 'expense_new',
            }
            return request.render('tour_guide_portal.portal_expense_new', values)

        # POST: 创建报账单
        try:
            Expense = request.env['hr.expense'].sudo()
            vals = {
                'name': kw.get('name', ''),
                'x_report_type': kw.get('x_report_type', 'expense'),
                'x_guide_id': guide.id,
                'employee_id': guide.employee_id.id if guide.employee_id else False,
                'date': kw.get('date') or fields.Date.today(),
                'product_id': int(kw['product_id']) if kw.get('product_id') else False,
                'quantity': float(kw.get('quantity', 1)),
                'total_amount': float(kw.get('total_amount', 0)),
                'x_invoice_no': kw.get('x_invoice_no', ''),
            }
            if kw.get('x_plan_id'):
                vals['x_plan_id'] = int(kw['x_plan_id'])
            if kw.get('x_loan_id'):
                vals['x_loan_id'] = int(kw['x_loan_id'])
            expense = Expense.create(vals)
            return request.redirect('/my/guide/expenses/%s' % expense.id)
        except (ValidationError, ValueError) as e:
            values = {'error': str(e), 'guide': guide, 'page_name': 'expense_new'}
            return request.render('tour_guide_portal.portal_expense_new', values)

    # === 门户首页 ===

    @http.route('/my/guide', type='http', auth='user', website=True)
    def portal_guide_home(self, **kw):
        guide = self._get_current_guide()
        if not guide:
            return request.render('tour_guide_portal.portal_guide_no_access')

        Task = request.env['project.task']
        Commission = request.env['tour.commission']
        Loan = request.env['tour.guide.loan']
        Expense = request.env['hr.expense']

        dispatch_count = Task.search_count(self._get_dispatch_domain(guide))
        commission_count = Commission.search_count(self._get_commission_domain(guide))
        loan_count = Loan.search_count(self._get_loan_domain(guide))
        expense_count = Expense.search_count(self._get_expense_domain(guide))

        recent_dispatches = Task.search(
            self._get_dispatch_domain(guide), order='date_start desc', limit=5)
        recent_commissions = Commission.search(
            self._get_commission_domain(guide), order='id desc', limit=5)

        values = {
            'guide': guide,
            'dispatch_count': dispatch_count,
            'commission_count': commission_count,
            'loan_count': loan_count,
            'expense_count': expense_count,
            'recent_dispatches': recent_dispatches,
            'recent_commissions': recent_commissions,
            'page_name': 'guide_home',
        }
        return request.render('tour_guide_portal.portal_guide_home', values)
