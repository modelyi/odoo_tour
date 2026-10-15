# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


def _get_or_create_account(env, code, name, account_type, **extra):
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        vals = {'code': code, 'name': name, 'account_type': account_type}
        vals.update(extra)
        acc = env['account.account'].create(vals)
    return acc


def _get_or_create_journal(env, jtype, name, code, **extra):
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
class TestCommissionReceipt(TransactionCase):
    """批6 P1-5（AC-17 菜单 [3622]）：佣金收款——
    凭证借 收款日记账默认科目 / 贷 1222 购物佣金应收（同 partner 闭环）、
    超额拦截、对账视图 paid_total 回流、批量收款向导。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # 收款需要带默认科目的银行日记账；佣金确认凭证需要杂项日记账
        cls.bank_account = _get_or_create_account(
            cls.env, '1003', '银行存款SK', 'asset_current')
        # 不回退存量银行日记账：其默认科目非 1003，借贷科目断言会错位
        cls.bank_journal = cls.env['account.journal'].search(
            [('code', '=', 'BNKSK'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.bank_journal:
            cls.bank_journal = cls.env['account.journal'].create({
                'name': '银行收款SK', 'code': 'BNKSK', 'type': 'bank',
                'company_id': cls.company.id,
                'default_account_id': cls.bank_account.id})
        cls.gen_journal = _get_or_create_journal(
            cls.env, 'general', '杂项日记账SK', 'GENSK')
        # 恢复库带入全局激活人均线会覆盖分成档 → 测试内屏蔽
        cls.env['ta.per.capita.line'].search(
            [('state', '=', 'active')]).write({'state': 'inactive'})

        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        route = cls.env['ta.route'].create({
            'name': '佣金收款测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '收款导游'})
        cls.u_guide = cls.env['res.users'].create({
            'name': '收款导游', 'login': 'rpt_g@test.local',
            'company_id': cls.company.id, 'partner_id': cls.guide.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_guide').id])]})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计SK', 'login': 'acct_sk@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})
        cls.dep.guide_ids = [(6, 0, [cls.u_guide.id])]

        cls.customer = cls.env['res.partner'].create({'name': '收款客户'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.customer.id, 'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()

        cls.shop_partner = cls.env['res.partner'].create(
            {'name': '收款购物店', 'supplier_rank': 1})
        cls.agreement = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 20.0})
        cls.agreement.action_active()
        cls.shop_partner2 = cls.env['res.partner'].create(
            {'name': '收款购物店B', 'supplier_rank': 1})
        cls.agreement2 = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner2.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 10.0})
        cls.agreement2.action_active()
        cls.staff_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': cls.guide.id,
            'tax_type': 'labor', 'id_number': '****7788',
            'share_rate': 40.0})
        cls.staff_agr.action_active()

    def _confirm_shop(self, partner, total):
        shop = self.env['ta.shop'].create({
            'departure_id': self.dep.id,
            'shop_partner_id': partner.id,
            'shop_date': '2026-11-02',
            'guest_count': 2,
            'total_amount': total,
            'guide_id': self.guide.id,
        })
        shop.with_user(self.u_acct).action_confirm()
        commission = self.env['ta.guide.commission'].search([
            ('departure_id', '=', self.dep.id),
            ('shop_partner_id', '=', partner.id)], limit=1)
        commission.with_user(self.u_acct).action_confirm()
        return commission

    def test_receipt_move_balanced(self):
        """收款凭证：借 银行存款 / 贷 1222 购物佣金应收，同 partner，借贷平衡。"""
        commission = self._confirm_shop(self.shop_partner, 10000.0)  # 佣金 2000
        receipt = self.env['ta.commission.receipt'].with_user(
            self.u_acct).create({
                'commission_id': commission.id,
                'date': '2026-11-05',
                'amount': 2000.0,
                'journal_id': self.bank_journal.id})
        self.assertEqual(commission.received_total, 2000.0)
        move = receipt.move_id.with_user(self.u_acct)
        self.assertTrue(move)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.journal_id, self.bank_journal)
        lines = {line.account_id.code: line for line in move.line_ids}
        self.assertAlmostEqual(lines['1003'].debit, 2000.0)
        self.assertAlmostEqual(lines['1222'].credit, 2000.0)
        self.assertEqual(lines['1003'].partner_id, self.shop_partner)
        self.assertEqual(lines['1222'].partner_id, self.shop_partner)
        self.assertAlmostEqual(
            sum(move.line_ids.mapped('debit')),
            sum(move.line_ids.mapped('credit')), places=2)

    def test_receipt_over_limit_blocked(self):
        """超额收款拦截：金额 > 佣金总额 − 已收。"""
        commission = self._confirm_shop(self.shop_partner, 10000.0)
        with self.assertRaises(UserError) as ctx:
            self.env['ta.commission.receipt'].with_user(
                self.u_acct).create({
                    'commission_id': commission.id,
                    'date': '2026-11-05',
                    'amount': 2500.0,
                    'journal_id': self.bank_journal.id})
        self.assertIn('未收余额', ctx.exception.args[0])
        self.assertFalse(commission.receipt_ids)

    def test_receipt_partial_then_limit(self):
        """部分收款后未收余额收敛，二次超额拦截。"""
        commission = self._confirm_shop(self.shop_partner, 10000.0)
        self.env['ta.commission.receipt'].with_user(self.u_acct).create({
            'commission_id': commission.id,
            'date': '2026-11-05', 'amount': 1200.0,
            'journal_id': self.bank_journal.id})
        self.assertEqual(commission.received_total, 1200.0)
        with self.assertRaises(UserError):
            self.env['ta.commission.receipt'].with_user(
                self.u_acct).create({
                    'commission_id': commission.id,
                    'date': '2026-11-06', 'amount': 801.0,
                    'journal_id': self.bank_journal.id})

    def test_paid_total_reflow(self):
        """对账视图 paid_total = Σ 收款金额（不再固定 0）。"""
        commission = self._confirm_shop(self.shop_partner, 10000.0)
        self.env['ta.commission.receipt'].with_user(self.u_acct).create({
            'commission_id': commission.id,
            'date': '2026-11-05', 'amount': 2000.0,
            'journal_id': self.bank_journal.id})
        self.env.flush_all()
        recon = self.env['ta.shop.reconciliation'].search([
            ('shop_partner_id', '=', self.shop_partner.id)])
        self.assertTrue(recon)
        self.assertAlmostEqual(recon.paid_total, 2000.0)

    def test_wizard_batch_collect(self):
        """批量向导：多选两单，预填未收余额，一次生成两张收款与凭证。"""
        c1 = self._confirm_shop(self.shop_partner, 10000.0)   # 2000
        c2 = self._confirm_shop(self.shop_partner2, 5000.0)   # 500
        Wizard = self.env['ta.commission.collect.wizard'].with_user(self.u_acct)
        defaults = Wizard.with_context(
            active_ids=[c1.id, c2.id]).default_get(['date', 'journal_id', 'line_ids'])
        wizard = Wizard.create(defaults)
        self.assertEqual(len(wizard.line_ids), 2)
        amounts = {line.commission_id.id: line.amount for line in wizard.line_ids}
        self.assertAlmostEqual(amounts[c1.id], 2000.0)
        self.assertAlmostEqual(amounts[c2.id], 500.0)
        wizard.journal_id = self.bank_journal.id
        wizard.action_collect()
        self.assertEqual(len(c1.receipt_ids), 1)
        self.assertEqual(len(c2.receipt_ids), 1)
        self.assertAlmostEqual(c1.received_total, 2000.0)
        self.assertAlmostEqual(c2.received_total, 500.0)
        for commission in (c1, c2):
            move = commission.receipt_ids[0].move_id.with_user(self.u_acct)
            self.assertEqual(move.state, 'posted')
            self.assertAlmostEqual(
                sum(move.line_ids.mapped('debit')),
                sum(move.line_ids.mapped('credit')), places=2)
