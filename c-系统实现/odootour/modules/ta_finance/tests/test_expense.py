# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, AccessError


@tagged('post_install', '-at_install')
class TestExpense(TransactionCase):
    """费用报销：提交→审核生成凭证（AC-05 非本人审核 + 幂等）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.expense_account = cls.env['account.account'].create({
            'name': '管理费用测试', 'code': '660901',
            'account_type': 'expense'})
        cls.payable_account = cls.env['account.account'].create({
            'name': '其他应付款测试', 'code': '224101',
            'account_type': 'liability_current'})
        cls.journal = cls.env['account.journal'].create({
            'name': '费用测试日记账', 'code': 'EXPTST', 'type': 'expense',
            'company_id': cls.company.id})
        cls.company.expense_account_id = cls.expense_account
        cls.env['ir.config_parameter'].sudo().set_param(
            'ta_finance.payable_employee_account_id', str(cls.payable_account.id))

        def mk(login, group_xmlids):
            groups = [cls.env.ref(g).id for g in group_xmlids] + [cls.env.ref('base.group_user').id]
            return cls.env['res.users'].create({
                'name': login, 'login': login + '@test.local',
                'company_id': cls.company.id,
                'group_ids': [(6, 0, groups)]})
        cls.u_sales = mk('exp_sales_t', ['ta_base.group_ta_sales'])
        cls.u_acct = mk('exp_acct_t', ['ta_base.group_ta_accountant'])

    def _expense(self, user=None, amount=500.0):
        return self.env['ta.expense'].with_user(user or self.u_sales).create({
            'reason': '测试报销', 'amount': amount,
            'expense_type': 'travel'})

    def test_approve_creates_move_and_idempotent(self):
        # T1.1 审核生成借贷平衡草稿凭证；重复审核被幂等拦截
        exp = self._expense()
        exp.action_submit()
        self.assertEqual(exp.state, 'submitted')
        exp.with_user(self.u_acct).action_approve()
        self.assertEqual(exp.state, 'approved')
        self.assertTrue(exp.move_id)
        self.assertEqual(exp.move_id.state, 'draft')
        self.assertAlmostEqual(exp.move_id.amount_total, 500.0)
        debit = exp.move_id.line_ids.filtered(lambda l: l.debit)
        credit = exp.move_id.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit.mapped('account_id'), self.expense_account)
        self.assertEqual(credit.mapped('account_id'), self.payable_account)
        moves_before = self.env['account.move'].search_count([])
        with self.assertRaises(UserError):
            exp.with_user(self.u_acct).action_approve()
        self.assertEqual(self.env['account.move'].search_count([]), moves_before)

    def test_self_approval_blocked(self):
        # T1.2 AC-05：审核人不能是报销人本人
        both = self.env['res.users'].create({
            'name': 'sales_acct_t', 'login': 'sales_acct_t@test.local',
            'company_id': self.company.id,
            'group_ids': [(6, 0, [self.env.ref('ta_base.group_ta_sales').id,
                                  self.env.ref('ta_base.group_ta_accountant').id,
                                  self.env.ref('base.group_user').id])]})
        exp = self._expense(user=both)
        exp.action_submit()
        with self.assertRaises(AccessError):
            exp.action_approve()

    def test_approve_requires_accountant(self):
        # T1.3 非会计审核被拦截
        exp = self._expense()
        exp.action_submit()
        with self.assertRaises(AccessError):
            exp.with_user(self.u_sales).action_approve()

    def test_amount_must_be_positive(self):
        # T1.4 金额约束
        with self.assertRaises(UserError):
            self._expense(amount=0)

    def test_reject_then_resubmit(self):
        exp = self._expense()
        exp.action_submit()
        exp.with_user(self.u_acct).action_reject()
        self.assertEqual(exp.state, 'rejected')
        exp.action_submit()
        self.assertEqual(exp.state, 'submitted')
