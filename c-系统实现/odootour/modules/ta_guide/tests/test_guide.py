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
class TestGuide(TransactionCase):
    """借款-发放-报账-佣金冲抵全链（BS-08 AC-18）+ 报账入单团成本。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.bank_account = _get_or_create_account(
            cls.env, '1003', '银行存款G', 'asset_current')
        cls.loan_account = _get_or_create_account(
            cls.env, '1221', '其他应收款-导游借款', 'asset_receivable')
        cls.env['ir.config_parameter'].sudo().set_int(
            'ta_guide.loan_account_id', cls.loan_account.id)
        cls.journal = _get_or_create_journal(
            cls.env, 'bank', '银行发放', 'BNKG',
            default_account_id=cls.bank_account.id)
        route = cls.env['ta.route'].create({
            'name': '导游测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '王导游'})
        cls.u_guide = cls.env['res.users'].create({
            'name': '王导游', 'login': 'guide_t@test.local',
            'company_id': cls.company.id, 'partner_id': cls.guide.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_guide').id])]})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计T', 'login': 'acct_g@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})

    def _loan(self, amount=2000.0):
        return self.env['ta.guide.loan'].create({
            'guide_id': self.guide.id, 'departure_id': self.dep.id,
            'amount': amount, 'journal_id': self.journal.id})

    def test_loan_flow_and_posted_move(self):
        loan = self._loan()
        loan.with_user(self.u_acct).action_approve()
        self.assertEqual(loan.state, 'approved')
        loan.with_user(self.u_acct).action_pay()
        self.assertEqual(loan.state, 'paid')
        self.assertEqual(loan.paid_move_id.state, 'posted')
        self.assertAlmostEqual(loan.outstanding, 2000.0)

    def test_loan_self_approve_blocked(self):
        loan = self._loan()
        # 导游本人即使有会计权限也不能自审（岗位分离延伸到借款）
        self.u_guide.group_ids = [(4, self.env.ref('ta_base.group_ta_accountant').id)]
        with self.assertRaises(AccessError):
            loan.with_user(self.u_guide).action_approve()

    def test_expense_flow_and_pnl(self):
        exp = self.env['ta.guide.expense'].with_user(self.u_guide).create({
            'departure_id': self.dep.id,
            'line_ids': [(0, 0, {'name': '餐费垫付', 'amount': 460.0, 'invoice_ref': 'FP001'})]})
        self.assertEqual(exp.guide_id, self.guide)
        exp.with_user(self.u_guide).action_submit()
        exp.with_user(self.u_acct).action_approve()
        self.assertEqual(exp.state, 'approved')
        self.env.flush_all()
        pnl = self.env['ta.team.pnl'].search([('departure_id', '=', self.dep.id)])
        self.assertAlmostEqual(pnl.guide_expense_total, 460.0)
        # 该团无收款/计调成本：毛利 = -(0 + 460)
        self.assertAlmostEqual(pnl.profit, -460.0)
        self.assertAlmostEqual(pnl.profit_tax_incl, -460.0)

    def test_expense_self_approve_blocked(self):
        exp = self.env['ta.guide.expense'].with_user(self.u_guide).create({
            'departure_id': self.dep.id,
            'line_ids': [(0, 0, {'name': '车费垫付', 'amount': 100.0})]})
        exp.with_user(self.u_guide).action_submit()
        self.u_guide.group_ids = [(4, self.env.ref('ta_base.group_ta_accountant').id)]
        with self.assertRaises(AccessError):
            exp.with_user(self.u_guide).action_approve()

    def test_commission_deduct_loan(self):
        loan = self._loan(2000.0)
        loan.with_user(self.u_acct).action_approve()
        loan.with_user(self.u_acct).action_pay()
        c = self.env['ta.guide.commission'].create({
            'guide_id': self.guide.id, 'departure_id': self.dep.id,
            'allowance': 3000.0, 'tax_rate': 0.10})
        self.assertAlmostEqual(c.tax_amount, 300.0)
        self.assertAlmostEqual(c.net_amount, 2700.0)
        c.with_user(self.u_acct).action_confirm()
        self.assertEqual(c.state, 'confirmed')
        c.with_user(self.u_acct).action_settle()
        self.assertEqual(c.state, 'settled')
        self.assertAlmostEqual(c.deducted_total, 2000.0)
        self.assertAlmostEqual(c.payable_rest, 700.0)
        self.assertEqual(loan.state, 'settled')
        self.assertAlmostEqual(loan.outstanding, 0.0)
        with self.assertRaises(UserError):
            c.with_user(self.u_acct).action_settle()  # 幂等 NFR-2

    def test_commission_partial_deduct(self):
        loan = self._loan(5000.0)
        loan.with_user(self.u_acct).action_approve()
        loan.with_user(self.u_acct).action_pay()
        c = self.env['ta.guide.commission'].create({
            'guide_id': self.guide.id, 'departure_id': self.dep.id,
            'allowance': 1000.0, 'tax_rate': 0.0})
        c.with_user(self.u_acct).action_confirm()
        c.with_user(self.u_acct).action_settle()
        self.assertAlmostEqual(c.deducted_total, 1000.0)
        self.assertAlmostEqual(loan.outstanding, 4000.0)
        self.assertEqual(loan.state, 'paid')
