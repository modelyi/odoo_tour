# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, AccessError


def _get_or_create_account(env, code, name, account_type, **extra):
    """幂等取数（范式同 scripts/seed_ta_demo.py）：search by code 命中即用。"""
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        vals = {'code': code, 'name': name, 'account_type': account_type}
        vals.update(extra)
        acc = env['account.account'].create(vals)
    return acc


def _get_or_create_journal(env, jtype, name, code, **extra):
    """幂等日记账：先按测试专属 code 找，再按类型找存量，都没有才建。"""
    J = env['account.journal']
    comp = env.company.id
    j = J.search([('code', '=', code), ('company_id', '=', comp)], limit=1) \
        or J.search([('type', '=', jtype), ('company_id', '=', comp)], limit=1)
    if not j:
        vals = {'name': name, 'code': code, 'type': jtype, 'company_id': comp}
        vals.update(extra)
        j = J.create(vals)
    return j


@tagged('post_install', '-at_install')
class TestExpense(TransactionCase):
    """费用报销：提交→审核生成凭证（AC-05 非本人审核 + 幂等）。

    注意：Odoo 20 中 account.move 仅会计/开票/采购组可读，凭证断言一律 with_user(会计)。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.expense_account = _get_or_create_account(
            cls.env, '660901', '管理费用测试', 'expense')
        cls.payable_account = _get_or_create_account(
            cls.env, '224101', '其他应付款测试', 'liability_current')
        cls.journal = _get_or_create_journal(
            cls.env, 'purchase', '费用测试日记账', 'EXPTST')
        cls.company.expense_account_id = cls.expense_account
        icp = cls.env['ir.config_parameter'].sudo()
        rec = icp.search([('key', '=', 'ta_finance.payable_employee_account_id')], limit=1)
        if rec:
            rec.value = str(cls.payable_account.id)
        else:
            icp.create({'key': 'ta_finance.payable_employee_account_id',
                        'value': str(cls.payable_account.id)})

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
        move = exp.sudo().move_id.with_user(self.u_acct)
        self.assertTrue(move)
        self.assertEqual(move.state, 'draft')
        self.assertAlmostEqual(move.amount_total, 500.0)
        debit = move.line_ids.filtered(lambda l: l.debit)
        credit = move.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit.mapped('account_id'), self.expense_account)
        self.assertEqual(credit.mapped('account_id'), self.payable_account)
        moves_before = self.env['account.move'].sudo().search_count([])
        with self.assertRaises(UserError):
            exp.with_user(self.u_acct).action_approve()
        self.assertEqual(self.env['account.move'].sudo().search_count([]), moves_before)

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
