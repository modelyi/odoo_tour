# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


def _get_or_create_journal(env, jtype, name, code, **extra):
    J = env['account.journal']
    comp = env.company.id
    j = J.search([('code', '=', code), ('company_id', '=', comp)], limit=1)
    if not j:
        vals = {'name': name, 'code': code, 'type': jtype, 'company_id': comp}
        vals.update(extra)
        j = J.create(vals)
    return j


@tagged('post_install', '-at_install')
class TestShopReturn(TransactionCase):
    """批6 P0-4（BS-08 §4.2 菜单 [4303]）：购物退单——草稿佣金重算、
    已确认佣金红冲（凭证反向、原单 cancel、新草稿单）、收款拦截（AC-17）、
    个税抵扣生成与下次确认自动抵减、重复确认拦截。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.gen_journal = _get_or_create_journal(
            cls.env, 'general', '杂项日记账TD', 'GENTD')
        # 恢复库带入全局生效人均线会覆盖分成档 → 测试内屏蔽
        cls.env['ta.per.capita.line'].search(
            [('state', '=', 'active')]).write({'state': 'inactive'})

        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        route = cls.env['ta.route'].create({
            'name': '退单测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '退单导游'})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计TD', 'login': 'acct_td@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})
        cls.dep.guide_ids = [(6, 0, [])]

        cls.customer = cls.env['res.partner'].create({'name': '退单客户'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.customer.id, 'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()

        cls.shop_partner = cls.env['res.partner'].create(
            {'name': '退单购物店', 'supplier_rank': 1})
        cls.agreement = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 20.0})
        cls.agreement.action_active()
        cls.staff_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': cls.guide.id,
            'tax_type': 'labor', 'id_number': '****3344',
            'share_rate': 40.0})
        cls.staff_agr.action_active()

    def _confirm_shop(self, total=10000.0, guest_count=2):
        shop = self.env['ta.shop'].create({
            'departure_id': self.dep.id,
            'shop_partner_id': self.shop_partner.id,
            'shop_date': '2026-11-02',
            'guest_count': guest_count,
            'total_amount': total,
            'guide_id': self.guide.id,
        })
        shop.with_user(self.u_acct).action_confirm()
        return shop

    def _commission(self):
        return self.env['ta.guide.commission'].search([
            ('departure_id', '=', self.dep.id),
            ('shop_partner_id', '=', self.shop_partner.id),
        ], limit=1)

    def _return(self, shop, amount):
        return self.env['ta.shop.return'].create({
            'shop_id': shop.id,
            'return_date': '2026-11-05',
            'return_amount': amount,
            'reason': '客户退货（测试）',
        })

    def test_draft_commission_recompute(self):
        """草稿佣金单：确认退单后按有效金额重算（不动原单状态）。"""
        shop = self._confirm_shop(10000.0)
        commission = self._commission()
        self.assertEqual(commission.state, 'draft')
        self.assertAlmostEqual(commission.commission_total, 2000.0)
        ret = self._return(shop, 3000.0)
        ret.with_user(self.u_acct).action_confirm()
        self.assertEqual(ret.state, 'confirmed')
        self.assertAlmostEqual(shop.return_amount_total, 3000.0)
        self.assertAlmostEqual(shop.effective_amount, 7000.0)
        self.assertEqual(commission.state, 'draft')
        self.assertAlmostEqual(commission.shop_amount, 7000.0)
        self.assertAlmostEqual(commission.commission_total, 1400.0)

    def test_confirmed_commission_reversed(self):
        """已确认佣金：红冲凭证反向过账，原单 cancel，新草稿单按有效金额生成。"""
        shop = self._confirm_shop(10000.0)
        commission = self._commission()
        commission.with_user(self.u_acct).action_confirm()
        move = commission.move_id.with_user(self.u_acct)
        self.assertEqual(move.state, 'posted')
        self.assertAlmostEqual(commission.commission_total, 2000.0)
        ret = self._return(shop, 3000.0)
        ret.with_user(self.u_acct).action_confirm()
        # 原单已取消
        self.assertEqual(commission.state, 'cancel')
        # 红冲凭证：posted、ref 标记、金额逐科目反向
        reverse = self.env['account.move'].with_user(self.u_acct).search([
            ('ref', '=', f"退单红冲 {ret.name} / {commission.name}")])
        self.assertTrue(reverse)
        self.assertEqual(reverse.state, 'posted')
        self.assertAlmostEqual(
            sum(reverse.line_ids.mapped('debit')),
            sum(reverse.line_ids.mapped('credit')), places=2)
        orig = {line.account_id.code: line for line in move.line_ids}
        for code, line in orig.items():
            rev_lines = reverse.line_ids.filtered(
                lambda l, c=code: l.account_id.code == c)
            self.assertEqual(len(rev_lines), 1, code)
            for rl in rev_lines:
                if line.debit:
                    self.assertAlmostEqual(rl.credit, line.debit, msg=code)
                if line.credit:
                    self.assertAlmostEqual(rl.debit, line.credit, msg=code)
        # 新草稿佣金单按有效金额 7000 生成
        new_commission = self._commission()
        self.assertNotEqual(new_commission.id, commission.id)
        self.assertEqual(new_commission.state, 'draft')
        self.assertAlmostEqual(new_commission.shop_amount, 7000.0)
        self.assertAlmostEqual(new_commission.commission_total, 1400.0)
        # 佣金+红冲后 1222 净额 = 新口径未确认（0）+ 原红冲归零
        self.assertFalse(new_commission.move_id)

    def test_return_blocked_by_receipt(self):
        """佣金已登记收款（AC-17）→ 退单确认拦截。"""
        shop = self._confirm_shop(10000.0)
        commission = self._commission()
        commission.with_user(self.u_acct).action_confirm()
        bank_journal = self.env['account.journal'].search([
            ('type', '=', 'bank'), ('company_id', '=', self.company.id)], limit=1)
        if not bank_journal.default_account_id:
            acc = self.env['account.account'].search(
                [('code', '=', '1003')], limit=1)
            if acc:
                bank_journal.default_account_id = acc.id
        self.assertTrue(bank_journal.default_account_id)
        self.env['ta.commission.receipt'].with_user(self.u_acct).create({
            'commission_id': commission.id,
            'date': '2026-11-04', 'amount': 500.0,
            'journal_id': bank_journal.id})
        ret = self._return(shop, 3000.0)
        with self.assertRaises(UserError) as ctx:
            ret.with_user(self.u_acct).action_confirm()
        self.assertIn('已登记收款', ctx.exception.args[0])
        self.assertEqual(ret.state, 'draft')
        self.assertEqual(commission.state, 'confirmed')

    def test_tax_deduct_generated_and_applied(self):
        """个税抵扣：退单生成 pending 抵扣；下次同人佣金确认自动抵减新个税。"""
        # 佣金 4000（20000×20%），导游 40% → 税前 1600 → 劳务个税 (1600-800)×20%=160
        shop = self._confirm_shop(20000.0)
        commission = self._commission()
        commission.with_user(self.u_acct).action_confirm()
        guide_row = commission.staff_line_ids.filtered(
            lambda r: r.staff_type == 'guide')
        self.assertAlmostEqual(guide_row.tax_amount, 160.0)
        ret = self._return(shop, 5000.0)
        ret.with_user(self.u_acct).action_confirm()
        # 抵扣记录 = 160 × 5000/20000 = 40
        deduct = ret.deduct_line_ids
        self.assertEqual(len(deduct), 1)
        self.assertAlmostEqual(deduct.amount, 40.0)
        self.assertEqual(deduct.state, 'pending')
        self.assertEqual(deduct.staff_id, self.guide)
        # 下次同人佣金（新发团同店 20000）：税前仍 1600 → 抵减 40 → 120
        route2 = self.env['ta.route'].create({
            'name': '退单抵扣测试线路2',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route2.action_on_sale()
        dep2 = self.env['ta.departure'].create({
            'route_id': route2.id, 'date_start': '2026-12-01',
            'date_end': '2026-12-03', 'seats_total': 10, 'seats_min': 2})
        dep2.action_open()
        dep2.action_confirm()
        order2 = self.env['ta.order'].create({
            'partner_id': self.customer.id, 'departure_id': dep2.id,
            'line_ids': [(0, 0, {'name': '丙', 'kind': 'adult'}),
                         (0, 0, {'name': '丁', 'kind': 'adult'})]})
        order2.action_confirm()
        shop2 = self.env['ta.shop'].create({
            'departure_id': dep2.id,
            'shop_partner_id': self.shop_partner.id,
            'shop_date': '2026-12-02',
            'guest_count': 2,
            'total_amount': 20000.0,
            'guide_id': self.guide.id,
        })
        shop2.with_user(self.u_acct).action_confirm()
        commission2 = self.env['ta.guide.commission'].search([
            ('departure_id', '=', dep2.id),
            ('shop_partner_id', '=', self.shop_partner.id)], limit=1)
        commission2.with_user(self.u_acct).action_confirm()
        guide_row2 = commission2.staff_line_ids.filtered(
            lambda r: r.staff_type == 'guide')
        self.assertAlmostEqual(guide_row2.tax_amount, 120.0)  # 160 − 40
        self.assertAlmostEqual(guide_row2.net_pay, 1600.0 - 120.0)
        deduct.invalidate_recordset()
        self.assertEqual(deduct.state, 'used')

    def test_duplicate_confirm_blocked(self):
        """重复确认拦截（幂等：仅 draft→confirmed）。"""
        shop = self._confirm_shop(10000.0)
        ret = self._return(shop, 1000.0)
        ret.with_user(self.u_acct).action_confirm()
        with self.assertRaises(UserError):
            ret.with_user(self.u_acct).action_confirm()

    def test_over_amount_blocked(self):
        """退单金额超过可退额度 → 拦截。"""
        shop = self._confirm_shop(10000.0)
        with self.assertRaises(UserError):
            self._return(shop, 11000.0)
        ret = self._return(shop, 6000.0)
        ret.with_user(self.u_acct).action_confirm()
        # 已确认退单 6000 → 可退额度 4000，再退 5000 拦截
        with self.assertRaises(UserError):
            self._return(shop, 5000.0)
        ret2 = self._return(shop, 4000.0)
        ret2.with_user(self.u_acct).action_confirm()
        self.assertAlmostEqual(shop.effective_amount, 0.0)
