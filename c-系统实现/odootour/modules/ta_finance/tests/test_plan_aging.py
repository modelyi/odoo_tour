# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPlanAging(TransactionCase):
    """迭代3：认领审核→期次先到先核销→反审核回退；应收账龄视图分桶。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.bank_account = cls.env['account.account'].create({
            'name': '银行存款3', 'code': '100231', 'account_type': 'asset_current'})
        cls.recv_account = cls.env['account.account'].create({
            'name': '应收账款3', 'code': '112231', 'account_type': 'asset_receivable'})
        cls.journal = cls.env['account.journal'].create({
            'name': '银行测试3', 'code': 'BNK3', 'type': 'bank',
            'company_id': cls.company.id,
            'default_account_id': cls.bank_account.id})
        cls.partner = cls.env['res.partner'].create({
            'name': '账龄客户',
            'property_account_receivable_id': cls.recv_account})
        route = cls.env['ta.route'].create({
            'name': '账龄测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 1500})]})
        route.action_on_sale()
        dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 2})
        dep.action_open()
        cls.dep = dep
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.partner.id, 'departure_id': dep.id,
            'line_ids': [(0, 0, {'name': '李四', 'kind': 'adult'})]})
        cls.order.action_confirm()

        def mk(login, group_xmlids):
            groups = [cls.env.ref(g).id for g in group_xmlids] + [cls.env.ref('base.group_user').id]
            return cls.env['res.users'].create({
                'name': login, 'login': login + '@test.local',
                'company_id': cls.company.id,
                'group_ids': [(6, 0, groups)]})
        cls.u_cashier = mk('cashier3_t', ['ta_base.group_ta_cashier'])
        cls.u_sales = mk('sales3_t', ['ta_base.group_ta_sales'])
        cls.u_acct = mk('acct3_t', ['ta_base.group_ta_accountant'])
        cls.u_mgr = mk('mgr3_t', ['ta_base.group_ta_manager'])

    def _plan(self, name, due, amount):
        return self.env['ta.receivable.plan'].create({
            'order_id': self.order.id, 'name': name,
            'due_date': due, 'amount': amount})

    def _claim_approve(self, amount):
        bank = self.env['ta.bank.line'].with_user(self.u_cashier).create({
            'amount': amount, 'journal_id': self.journal.id,
            'partner_name': '账龄客户', 'ref': 'AGING-%s' % amount})
        claim = self.env['ta.payment.claim'].with_user(self.u_sales).create({
            'line_ids': [(0, 0, {'bank_line_id': bank.id, 'amount': amount})],
            'alloc_ids': [(0, 0, {'order_id': self.order.id,
                                  'amount_allocated': amount})]})
        claim.action_submit()
        claim.with_user(self.u_acct).action_approve()
        return claim

    def test_plan_allocation_and_revert(self):
        # T3.1 期次先到先核销 + 反审核回退
        self.order.plan_ids.unlink()  # 去掉确认时自动生成的"全额"期次
        p1 = self._plan('订金', '2026-01-10', 500)
        p2 = self._plan('尾款', '2026-02-10', 1000)
        claim = self._claim_approve(600)
        self.assertAlmostEqual(p1.amount_paid, 500)
        self.assertAlmostEqual(p2.amount_paid, 100)
        self.assertIn(claim, p1.claim_ids + p2.claim_ids)
        self.assertAlmostEqual(self.order.amount_paid, 600)
        claim.with_user(self.u_mgr).action_reverse()
        self.assertAlmostEqual(p1.amount_paid, 0)
        self.assertAlmostEqual(p2.amount_paid, 0)
        self.assertFalse((p1 + p2).claim_ids)

    def test_aging_buckets(self):
        # T3.2 账龄分桶：今天/45天/75天/200天 锚点各归其桶
        today = fields.Date.context_today(self)
        cases = [
            (500, today, 'b0_30'),
            (600, today - relativedelta(days=45), 'b31_60'),
            (700, today - relativedelta(days=75), 'b61_90'),
            (800, today - relativedelta(days=200), 'b90p'),
        ]
        order = self.order
        order.plan_ids.unlink()        for i, (amt, due, _b) in enumerate(cases):
            self.env['ta.receivable.plan'].create({
                'order_id': order.id, 'name': '期%d' % i,
                'due_date': due, 'amount': amt})
        self.env.flush_all()
        rows = self.env['ta.receivable.aging'].search([('order_id', '=', order.id)])
        self.assertEqual(len(rows), 1, 'order 维度一行')
        row = rows
        self.assertAlmostEqual(row.amount_open, 2600)
        self.assertEqual(row.date_oldest, min(d for _a, d, _b in cases))
        self.assertEqual(row.bucket, 'b90p')  # 锚点=最早未清期次 → 200 天
        self.assertGreaterEqual(row.days_overdue, 199)
