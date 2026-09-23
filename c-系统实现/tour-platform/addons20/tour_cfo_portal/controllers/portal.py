# -*- coding: utf-8 -*-
from collections import OrderedDict

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PortalCFO(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if not self._is_cfo_user():
            return values

        if 'expense_approval_count' in counters:
            values['expense_approval_count'] = request.env['hr.expense'].search_count(
                self._get_expense_approval_domain())
        if 'commission_approval_count' in counters:
            values['commission_approval_count'] = request.env['tour.commission'].search_count(
                self._get_commission_approval_domain())
        if 'loan_approval_count' in counters:
            values['loan_approval_count'] = request.env['tour.guide.loan'].search_count(
                self._get_loan_approval_domain())
        return values

    def _is_cfo_user(self):
        """检查当前用户是否为 CFO 角色"""
        cfo_group = request.env.ref('tour_cfo_portal.group_cfo_portal', raise_if_not_found=False)
        if not cfo_group:
            return False
        return cfo_group in request.env.user.group_ids

    # === 审批域定义 ===

    def _get_expense_approval_domain(self):
        """待审批报账"""
        return [('state', 'in', ['reported', 'submitted'])]

    def _get_commission_approval_domain(self):
        """待审批佣金"""
        return [('state', '=', 'calculated')]

    def _get_loan_approval_domain(self):
        """待审批借款"""
        return [('state', '=', 'requested')]

    # === CFO 门户首页 ===

    @http.route('/my/cfo', type='http', auth='user', website=True)
    def portal_cfo_home(self, **kw):
        if not self._is_cfo_user():
            return request.render('tour_cfo_portal.portal_cfo_no_access')

        Expense = request.env['hr.expense']
        Commission = request.env['tour.commission']
        Loan = request.env['tour.guide.loan']

        # 统计数据
        expense_approval_count = Expense.search_count(self._get_expense_approval_domain())
        commission_approval_count = Commission.search_count(self._get_commission_approval_domain())
        loan_approval_count = Loan.search_count(self._get_loan_approval_domain())

        # 待审批列表
        recent_expenses = Expense.search(
            self._get_expense_approval_domain(),
            order='date desc', limit=10)
        recent_commissions = Commission.search(
            self._get_commission_approval_domain(),
            order='create_date desc', limit=10)
        recent_loans = Loan.search(
            self._get_loan_approval_domain(),
            order='apply_date desc', limit=10)

        # 财务汇总
        total_pending_expenses = sum(exp.total_amount for exp in recent_expenses)
        total_pending_commissions = sum(com.amount for com in recent_commissions)
        total_pending_loans = sum(loan.amount for loan in recent_loans)

        values = {
            'expense_approval_count': expense_approval_count,
            'commission_approval_count': commission_approval_count,
            'loan_approval_count': loan_approval_count,
            'recent_expenses': recent_expenses,
            'recent_commissions': recent_commissions,
            'recent_loans': recent_loans,
            'total_pending_expenses': total_pending_expenses,
            'total_pending_commissions': total_pending_commissions,
            'total_pending_loans': total_pending_loans,
            'page_name': 'cfo_home',
        }
        return request.render('tour_cfo_portal.portal_cfo_home', values)

    # === 报账审批 ===

    @http.route(['/my/cfo/expenses', '/my/cfo/expenses/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_cfo_expenses(self, page=1, **kw):
        if not self._is_cfo_user():
            return request.render('tour_cfo_portal.portal_cfo_no_access')

        Expense = request.env['hr.expense']
        domain = self._get_expense_approval_domain()

        # 搜索和过滤
        searchbar_sortings = {
            'date': {'label': _('报账日期'), 'order': 'date desc'},
            'amount': {'label': _('金额'), 'order': 'total_amount desc'},
            'state': {'label': _('状态'), 'order': 'state'},
        }
        sort_label = kw.get('sortby', 'date')
        sort_order = searchbar_sortings.get(sort_label, searchbar_sortings['date'])['order']

        expenses = Expense.search(domain, order=sort_order)

        # 分页
        pager = portal_pager(
            url='/my/cfo/expenses',
            url_args={'sortby': sort_label},
            total=len(expenses),
            page=page,
            step=20,
        )
        expenses = expenses[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'expenses': expenses,
            'page_name': 'cfo_expenses',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sort_label,
            'default_sortby': 'date',
        }
        return request.render('tour_cfo_portal.portal_cfo_expenses', values)

    @http.route('/my/cfo/expenses/<int:expense_id>',
                type='http', auth='user', website=True)
    def portal_cfo_expense_detail(self, expense_id, **kw):
        if not self._is_cfo_user():
            return request.render('tour_cfo_portal.portal_cfo_no_access')

        expense = request.env['hr.expense'].sudo().browse(expense_id)
        if not expense.exists():
            raise MissingError(_('此报账记录不存在'))

        attachments = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'hr.expense'),
            ('res_id', '=', expense.id),
        ], order='create_date desc')

        values = {
            'expense': expense,
            'attachments': attachments,
            'page_name': 'cfo_expense_detail',
        }
        return request.render('tour_cfo_portal.portal_cfo_expense_detail', values)

    @http.route('/my/cfo/expenses/<int:expense_id>/approve',
                type='http', auth='user', website=True, methods=['POST'])
    def portal_cfo_expense_approve(self, expense_id, **kw):
        if not self._is_cfo_user():
            return request.render('tour_cfo_portal.portal_cfo_no_access')

        expense = request.env['hr.expense'].sudo().browse(expense_id)
        if not expense.exists():
            raise MissingError(_('此报账记录不存在'))

        try:
            expense.action_approve()
            return request.redirect('/my/cfo/expenses/%s' % expense_id)
        except Exception as e:
            values = {
                'error': str(e),
                'expense': expense,
                'page_name': 'cfo_expense_detail',
            }
            return request.render('tour_cfo_portal.portal_cfo_expense_detail', values)

    # === 佣金审批 ===

    @http.route(['/my/cfo/commissions', '/my/cfo/commissions/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_cfo_commissions(self, page=1, **kw):
        if not self._is_cfo_user():
            return request.render('tour_cfo_portal.portal_cfo_no_access')

        Commission = request.env['tour.commission']
        domain = self._get_commission_approval_domain()

        commissions = Commission.search(domain, order='create_date desc')

        pager = portal_pager(
            url='/my/cfo/commissions',
            total=len(commissions),
            page=page,
            step=20,
        )
        commissions = commissions[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'commissions': commissions,
            'page_name': 'cfo_commissions',
            'pager': pager,
        }
        return request.render('tour_cfo_portal.portal_cfo_commissions', values)

    # === 借款审批 ===

    @http.route(['/my/cfo/loans', '/my/cfo/loans/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_cfo_loans(self, page=1, **kw):
        if not self._is_cfo_user():
            return request.render('tour_cfo_portal.portal_cfo_no_access')

        Loan = request.env['tour.guide.loan']
        domain = self._get_loan_approval_domain()

        loans = Loan.search(domain, order='apply_date desc')

        pager = portal_pager(
            url='/my/cfo/loans',
            total=len(loans),
            page=page,
            step=20,
        )
        loans = loans[(pager['offset']):(pager['offset'] + 20)]

        values = {
            'loans': loans,
            'page_name': 'cfo_loans',
            'pager': pager,
        }
        return request.render('tour_cfo_portal.portal_cfo_loans', values)

    # === 附件下载 ===

    @http.route('/my/cfo/expenses/<int:expense_id>/attachment/<int:attachment_id>',
                type='http', auth='user', website=False)
    def portal_cfo_expense_attachment_download(self, expense_id, attachment_id, **kw):
        if not self._is_cfo_user():
            raise AccessError(_('无权访问'))

        expense = request.env['hr.expense'].sudo().browse(expense_id)
        if not expense.exists():
            raise MissingError(_('报账记录不存在'))

        attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
        if attachment.res_model != 'hr.expense' or attachment.res_id != expense.id:
            raise AccessError(_('附件不属于此报账记录'))

        attachment.generate_access_token()
        return request.redirect('/web/content/%s?download=true&access_token=%s' % (
            attachment.id, attachment.access_token))
