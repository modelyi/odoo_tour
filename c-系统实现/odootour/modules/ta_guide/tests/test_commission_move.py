# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, AccessError


def _get_or_create_account(env, code, name, account_type, **extra):
    """幂等取数（范式同 test_guide.py）：search by code 命中即用。"""
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
class TestCommissionMove(TransactionCase):
    """批5-迭代1：P0-1 佣金确认凭证（BS-08 §4.10.1/4.10.2 + AC-19 销项税）
    与 §4.10.4 借款冲抵凭证；科目解析 get_or_create、语义复用、中文 UserError、
    重复确认守卫。Odoo 20：account.move 断言一律 with_user(会计)。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # 凭证落账环境：杂项日记账（确认/冲抵凭证）+ 借款发放的银行日记账与 1221 科目
        cls.gen_journal = _get_or_create_journal(
            cls.env, 'general', '杂项测试日记账', 'GENTST')
        cls.bank_account = _get_or_create_account(
            cls.env, '1003', '银行存款G', 'asset_current')
        cls.loan_account = _get_or_create_account(
            cls.env, '1221', '其他应收款-导游借款', 'asset_receivable')
        cls.env['ir.config_parameter'].sudo().set_int(
            'ta_guide.loan_account_id', cls.loan_account.id)
        cls.bank_journal = _get_or_create_journal(
            cls.env, 'bank', '银行发放', 'BNKGM', default_account_id=cls.bank_account.id)
        # AC-19：购物路径增值税率 6%（价税分离），引擎据此计算 commission_tax
        cls.env['ir.config_parameter'].sudo().set_float('ta_base.default_tax_rate', 0.06)

        route = cls.env['ta.route'].create({
            'name': '佣金凭证测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '凭证导游'})
        cls.u_guide = cls.env['res.users'].create({
            'name': '凭证导游', 'login': 'cmoveg_t@test.local',
            'company_id': cls.company.id, 'partner_id': cls.guide.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_guide').id])]})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计V', 'login': 'acct_v@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})
        cls.dep.guide_ids = [(6, 0, [cls.u_guide.id])]

        cls.customer = cls.env['res.partner'].create({'name': '凭证客户'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.customer.id, 'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()  # heads=2

        cls.shop_partner = cls.env['res.partner'].create(
            {'name': '凭证购物店', 'supplier_rank': 1})
        cls.agreement = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 15.0,
            'tier_rule_ids': [
                (0, 0, {'min_per_capita': 0.0, 'max_per_capita': 1000.0,
                        'commission_rate': 20.0}),
                (0, 0, {'min_per_capita': 1000.0, 'max_per_capita': 5000.0,
                        'commission_rate': 25.0}),
                (0, 0, {'min_per_capita': 5000.0, 'commission_rate': 30.0}),
            ]})
        cls.agreement.action_active()

        cls.staff_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': cls.guide.id,
            'tax_type': 'labor', 'id_number': '****1234',
            'share_rate': 40.0,
            'premium_rule_ids': [
                (0, 0, {'min_per_capita': 2500.0, 'premium_amount': 300.0}),
                (0, 0, {'min_per_capita': 5000.0, 'premium_amount': 500.0}),
            ]})
        cls.staff_agr.action_active()

    # ---- 辅助 ----
    def _shop(self, amount=10000.0, guest_count=2):
        return self.env['ta.shop'].create({
            'departure_id': self.dep.id,
            'shop_partner_id': self.shop_partner.id,
            'shop_date': '2026-11-02',
            'guest_count': guest_count,
            'total_amount': amount,
            'guide_id': self.guide.id,
        })

    def _commission(self):
        return self.env['ta.guide.commission'].search([
            ('departure_id', '=', self.dep.id),
            ('shop_partner_id', '=', self.shop_partner.id),
        ])

    def _manual(self, allowance=3000.0, tax_rate=0.10):
        return self.env['ta.guide.commission'].create({
            'guide_id': self.guide.id, 'departure_id': self.dep.id,
            'allowance': allowance, 'tax_rate': tax_rate})

    def _lines_by_code(self, move):
        """本次凭证各科目只出现一次，按科目 code 建索引。"""
        return {line.account_id.code: line for line in move.line_ids}

    # ---- ① 购物路径：6 行凭证（BS-08 §4.10 表共 6 行，任务标题"5 行"系笔误），
    #          借贷平衡，科目金额符合 BS-08 §4.10 表 ----
    def test_shop_confirm_move_6_lines(self):
        shop = self._shop()
        shop.with_user(self.u_acct).action_confirm()
        c = self._commission()
        self.assertEqual(c.state, 'draft')
        self.assertAlmostEqual(c.commission_total, 3000.0)      # 10000×30%
        self.assertAlmostEqual(c.commission_tax, 169.81)        # 3000×6%/1.06
        self.assertAlmostEqual(c.allowance, 1700.0)             # 1200+500
        self.assertAlmostEqual(c.tax_amount, 180.0)
        self.assertAlmostEqual(c.net_amount, 1520.0)
        c.with_user(self.u_acct).action_confirm()
        self.assertEqual(c.state, 'confirmed')
        move = c.move_id.with_user(self.u_acct)
        self.assertTrue(move)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.journal_id, self.gen_journal)
        self.assertIn(c.name, move.ref)
        self.assertEqual(len(move.line_ids), 6)
        lines = self._lines_by_code(move)
        recv = lines['1222']
        self.assertAlmostEqual(recv.debit, 3000.0)
        self.assertEqual(recv.partner_id, self.shop_partner)    # 购物店应付佣金
        income = lines['6051']
        self.assertAlmostEqual(income.credit, 2830.19)          # 3000-169.81（不含税）
        vat = lines['222101']
        self.assertAlmostEqual(vat.credit, 169.81)              # AC-19 销项税额
        cost = lines['6407']
        self.assertAlmostEqual(cost.debit, 1700.0)              # 分成+奖金
        payable = lines['2241']
        self.assertAlmostEqual(payable.credit, 1520.0)          # 税后实发
        wh_tax = lines['222102']
        self.assertAlmostEqual(wh_tax.credit, 180.0)            # 代扣个税
        self.assertAlmostEqual(
            sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')), places=2)

    # ---- ② 手工路径：3 行凭证，借贷平衡 ----
    def test_manual_confirm_move_3_lines(self):
        c = self._manual()
        self.assertAlmostEqual(c.tax_amount, 300.0)
        self.assertAlmostEqual(c.net_amount, 2700.0)
        c.with_user(self.u_acct).action_confirm()
        move = c.move_id.with_user(self.u_acct)
        self.assertTrue(move)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(len(move.line_ids), 3)
        lines = self._lines_by_code(move)
        cost = lines['6407']
        self.assertAlmostEqual(cost.debit, 3000.0)
        payable = lines['2241']
        self.assertAlmostEqual(payable.credit, 2700.0)
        wh_tax = lines['222102']
        self.assertAlmostEqual(wh_tax.credit, 300.0)
        self.assertAlmostEqual(
            sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')), places=2)

    # ---- ③ 科目缺失且创建受限 → 中文 UserError，绝不静默跳过 ----
    def test_missing_account_raises_chinese_usererror(self):
        c = self._manual(allowance=1000.0, tax_rate=0.0)
        Account = type(self.env['account.account'])
        with mock.patch.object(Account, 'create',
                               side_effect=AccessError('创建受限')):
            with self.assertRaises(UserError) as ctx:
                c.with_user(self.u_acct).action_confirm()
        self.assertIn('科目', ctx.exception.args[0])
        self.assertIn('请会计', ctx.exception.args[0])
        self.assertEqual(c.state, 'draft')
        self.assertFalse(c.move_id)

    # ---- ④ 重复确认被 state 守卫拦截，凭证只生成一次 ----
    def test_duplicate_confirm_blocked(self):
        c = self._manual(allowance=1000.0, tax_rate=0.0)
        c.with_user(self.u_acct).action_confirm()
        self.assertTrue(c.move_id)
        moves_before = self.env['account.move'].sudo().search_count([])
        with self.assertRaises(UserError):
            c.with_user(self.u_acct).action_confirm()
        self.assertEqual(self.env['account.move'].sudo().search_count([]), moves_before)

    # ---- ⑤ §4.10.4 借款冲抵凭证：借 2241 / 贷 1221，对冲借款发放分录 ----
    def test_settle_offset_move(self):
        loan = self.env['ta.guide.loan'].create({
            'guide_id': self.guide.id, 'departure_id': self.dep.id,
            'amount': 2000.0, 'journal_id': self.bank_journal.id})
        loan.with_user(self.u_acct).action_approve()
        loan.with_user(self.u_acct).action_pay()
        pay_move = loan.paid_move_id
        self.assertTrue(pay_move)
        c = self._manual()
        c.with_user(self.u_acct).action_confirm()
        c.with_user(self.u_acct).action_settle()
        self.assertEqual(c.state, 'settled')
        settle_move = c.settle_move_id.with_user(self.u_acct)
        self.assertTrue(settle_move)
        self.assertEqual(settle_move.state, 'posted')
        self.assertEqual(len(settle_move.line_ids), 2)
        debit = settle_move.line_ids.filtered(lambda l: l.debit)
        credit = settle_move.line_ids.filtered(lambda l: l.credit)
        self.assertAlmostEqual(debit.debit, 2000.0)
        self.assertAlmostEqual(credit.credit, 2000.0)
        self.assertEqual(debit.account_id.code, '2241')         # 其他应付款-导游分成
        self.assertEqual(credit.account_id, self.loan_account)  # 1221 与发放借方同一科目
        self.assertEqual(loan.state, 'settled')
        self.assertAlmostEqual(loan.outstanding, 0.0)
        # 已有发放凭证不受影响（全库借贷平衡不变量）
        self.assertAlmostEqual(
            sum(pay_move.line_ids.mapped('debit')),
            sum(pay_move.line_ids.mapped('credit')), places=2)

    # ---- ⑥ 语义匹配的既有科目直接复用，不重复创建 ----
    def test_reuse_existing_payable_account(self):
        existing = _get_or_create_account(
            self.env, '2241', '其他应付款', 'liability_payable')
        c = self._manual(allowance=1000.0, tax_rate=0.0)
        c.with_user(self.u_acct).action_confirm()
        payable_line = c.move_id.with_user(self.u_acct).line_ids.filtered(
            lambda l: l.credit and l.account_id.code == '2241')
        self.assertEqual(payable_line.account_id, existing)
        self.assertEqual(
            self.env['account.account'].search([('code', '=', '2241')]), existing)

    # ---- ⑦ 税率未配置：销项行金额 0、收入行=全额，仍平衡且不报错 ----
    def test_zero_vat_rate_balanced(self):
        self.env['ir.config_parameter'].sudo().set_float('ta_base.default_tax_rate', 0.0)
        shop = self._shop()
        shop.with_user(self.u_acct).action_confirm()
        c = self._commission()
        self.assertAlmostEqual(c.commission_tax, 0.0)
        c.with_user(self.u_acct).action_confirm()
        move = c.move_id.with_user(self.u_acct)
        self.assertEqual(len(move.line_ids), 6)
        income = move.line_ids.filtered(lambda l: l.account_id.code == '6051')
        vat = move.line_ids.filtered(
            lambda l: l.account_id.code == '222101')
        self.assertAlmostEqual(income.credit, 3000.0)
        self.assertAlmostEqual(vat.credit, 0.0)
        self.assertAlmostEqual(
            sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')), places=2)
