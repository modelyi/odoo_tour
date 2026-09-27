# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, AccessError


@tagged('post_install', '-at_install')
class TestClaim(TransactionCase):
    """三步闭环（登记→认领→审核）+ AC-05 岗位分离 + 幂等 + 反审核。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # --- 最小会计环境（影子库无演示数据）---
        cls.bank_account = cls.env['account.account'].create({
            'name': '银行存款', 'code': '1002',
            'account_type': 'asset_current'})
        cls.recv_account = cls.env['account.account'].create({
            'name': '应收账款', 'code': '1122',
            'account_type': 'asset_receivable'})
        cls.journal = cls.env['account.journal'].create({
            'name': '银行测试', 'code': 'BNKT', 'type': 'bank',
            'company_id': cls.company.id,
            'default_account_id': cls.bank_account.id})
        cls.partner = cls.env['res.partner'].create({
            'name': '测试客户',
            'property_account_receivable_id': cls.recv_account.id})
        # --- 业务环境：线路→发团计划→订单（已确认，总额 3000）---
        route = cls.env['ta.route'].create({
            'name': '收款测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 2})
        dep.action_open()
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.partner.id, 'departure_id': dep.id,
            'line_ids': [(0, 0, {'name': '张三', 'kind': 'adult'})]})
        cls.order.action_confirm()
        # --- 岗位用户 ---
        def mk(login, group_xmlids):
            groups = [cls.env.ref(g).id for g in group_xmlids] + [cls.env.ref('base.group_user').id]
            return cls.env['res.users'].create({
                'name': login, 'login': login + '@test.local',
                'company_id': cls.company.id,
                'group_ids': [(6, 0, groups)]})
        cls.u_cashier = mk('cashier_t', ['ta_base.group_ta_cashier'])
        cls.u_sales = mk('sales_t', ['ta_base.group_ta_sales'])
        cls.u_sales_acct = mk('sales_acct_t',
                              ['ta_base.group_ta_sales', 'ta_base.group_ta_accountant'])
        cls.u_cashier_acct = mk('cashier_acct_t',
                                ['ta_base.group_ta_cashier', 'ta_base.group_ta_accountant'])
        cls.u_acct = mk('acct_t', ['ta_base.group_ta_accountant'])
        cls.u_mgr = mk('mgr_t', ['ta_base.group_ta_manager'])

    # ---- helpers ----
    def _bank_line_env(self, user, amount=3000.0):
        return self.env['ta.bank.line'].with_user(user).create({
            'amount': amount, 'journal_id': self.journal.id,
            'partner_name': '测试客户', 'ref': 'TEST-%s' % user.login})

    def _claim(self, user, source_amount=3000.0, alloc_amount=3000.0, bank=None):
        bank = bank or self._bank_line_env(user=self.u_cashier, amount=source_amount)
        return self.env['ta.payment.claim'].with_user(user).create({
            'line_ids': [(0, 0, {'bank_line_id': bank.id, 'amount': source_amount})],
            'alloc_ids': [(0, 0, {'order_id': self.order.id,
                                  'amount_allocated': alloc_amount})]})

    # ---- 测试 ----
    def test_full_loop(self):
        claim = self._claim(self.u_sales)
        claim.action_submit()
        self.assertEqual(claim.state, 'submitted')
        claim.with_user(self.u_acct).action_approve()
        self.assertEqual(claim.state, 'approved')
        self.assertTrue(claim.move_id)
        self.assertEqual(claim.move_id.state, 'posted')
        self.assertAlmostEqual(self.order.amount_paid, 3000.0)
        self.assertAlmostEqual(claim.move_id.amount_total, 3000.0)
        bank = claim.line_ids.bank_line_id
        self.assertEqual(bank.state, 'claimed')
        self.assertAlmostEqual(bank.residual, 0.0)

    def test_ac05_approver_not_claimer(self):
        claim = self._claim(self.u_sales_acct)
        claim.action_submit()
        with self.assertRaises(AccessError):
            claim.action_approve()  # 同一人：认领人=审核人

    def test_ac05_approver_not_registrant(self):
        bank = self._bank_line_env(self.u_cashier_acct)
        claim = self._claim(self.u_sales, bank=bank)
        claim.action_submit()
        with self.assertRaises(AccessError):
            claim.with_user(self.u_cashier_acct).action_approve()  # 登记人=审核人

    def test_approve_requires_accountant(self):
        claim = self._claim(self.u_sales)
        claim.action_submit()
        # 无会计权限的用户（仅计调）审核被组校验拦截：
        u_disp = self.env['res.users'].create({
            'name': 'disp_t', 'login': 'disp_t@test.local',
            'company_id': self.company.id,
            'group_ids': [(6, 0, [self.env.ref('ta_base.group_ta_dispatcher').id,
                                  self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):
            claim.with_user(u_disp).action_approve()

    def test_submit_imbalance(self):
        claim = self._claim(self.u_sales, source_amount=3000.0, alloc_amount=2000.0)
        with self.assertRaises(UserError):
            claim.action_submit()

    def test_overclaim_reserved_blocks_second_submit(self):
        bank = self._bank_line_env(self.u_cashier, amount=3000.0)
        c1 = self._claim(self.u_sales, bank=bank)
        c1.action_submit()
        c2 = self._claim(self.u_sales, bank=bank)
        with self.assertRaises(UserError):
            c2.action_submit()  # 已被 c1 预约占用

    def test_approve_twice_no_second_move(self):
        claim = self._claim(self.u_sales)
        claim.action_submit()
        claim.with_user(self.u_acct).action_approve()
        moves_before = self.env['account.move'].search_count([])
        with self.assertRaises(UserError):
            claim.with_user(self.u_acct).action_approve()
        self.assertEqual(self.env['account.move'].search_count([]), moves_before)

    def test_reverse_restores_paid(self):
        claim = self._claim(self.u_sales)
        claim.action_submit()
        claim.with_user(self.u_acct).action_approve()
        claim.with_user(self.u_mgr).action_reverse()
        self.assertEqual(claim.state, 'draft')
        self.assertFalse(claim.move_id)
        self.assertAlmostEqual(self.order.amount_paid, 0.0)
        rev = self.env['account.move'].search(
            [('reversed_entry_id', '!=', False)])
        self.assertTrue(rev, '应存在红冲凭证')

    def test_reject_then_resubmit(self):
        claim = self._claim(self.u_sales)
        claim.action_submit()
        claim.with_user(self.u_acct).action_reject()
        self.assertEqual(claim.state, 'rejected')
        claim.action_submit()
        self.assertEqual(claim.state, 'submitted')
