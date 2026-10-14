# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, AccessError


def _get_or_create_account(env, code, name, account_type, **extra):
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        vals = {'code': code, 'name': name, 'account_type': account_type}
        vals.update(extra)
        acc = env['account.account'].create(vals)
    return acc


def _get_or_create_journal(env, jtype, name, code, **extra):
    comp = env.company.id
    j = env['account.journal'].search([('code', '=', code), ('company_id', '=', comp)], limit=1) \
        or env['account.journal'].search([('type', '=', jtype), ('company_id', '=', comp)], limit=1)
    if not j:
        vals = {'name': name, 'code': code, 'type': jtype, 'company_id': comp}
        vals.update(extra)
        j = env['account.journal'].create(vals)
    return j


def _get_or_create_biz_mode(env, code, name):
    mode = env['ta.biz.mode'].search([('code', '=', code)], limit=1)
    if not mode:
        mode = env['ta.biz.mode'].create({'code': code, 'name': name})
    return mode


@tagged('post_install', '-at_install')
class TestRevenueRecognition(TransactionCase):
    """批6 P0-6：发团日收入确认（总额法拆税 / 41 差价 / 配置开关 / 幂等 / 认领对冲）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.ta_taxpayer_type = 'general'
        cls.company.ta_vat_rate = 0.06
        cls.company.ta_revenue_dd_split_tax = False
        cls.company.ta_revenue_auto_on_depart = True
        cls.recv_account = _get_or_create_account(
            cls.env, '1122', '应收账款-finance测试', 'asset_receivable')
        cls.bank_account = _get_or_create_account(
            cls.env, '1002', '银行存款-finance测试', 'asset_current')
        cls.bank_journal = _get_or_create_journal(
            cls.env, 'bank', '银行测试-finance', 'BNKT',
            default_account_id=cls.bank_account.id)
        cls.sale_journal = _get_or_create_journal(
            cls.env, 'sale', '销售测试-finance', 'SALET')
        _get_or_create_journal(cls.env, 'purchase', '采购测试-finance', 'PURT')
        cls.partner = cls.env['res.partner'].create({
            'name': '收入确认测试客户',
            'property_account_receivable_id': cls.recv_account.id})
        cls.mode_gross = _get_or_create_biz_mode(cls.env, '1', '组团')
        cls.mode_dd = _get_or_create_biz_mode(cls.env, '41', '代订')

        def mk(login, group_xmlids):
            groups = [cls.env.ref(g).id for g in group_xmlids] \
                + [cls.env.ref('base.group_user').id]
            return cls.env['res.users'].create({
                'name': login, 'login': login + '@test.local',
                'company_id': cls.company.id,
                'group_ids': [(6, 0, groups)]})
        cls.u_sales = mk('rev_sales', ['ta_base.group_ta_sales'])
        cls.u_acct = mk('rev_acct', ['ta_base.group_ta_accountant'])
        cls.u_mgr = mk('rev_mgr', ['ta_base.group_ta_manager'])

    def _route(self, prices):
        route = self.env['ta.route'].create({
            'name': '收入确认测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': k, 'amount': a}) for k, a in prices],
        })
        route.action_on_sale()
        return route

    def _departure(self, route, mode=None, seats=10):
        dep = self.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-10-01',
            'seats_total': seats, 'seats_min': 1,
            'biz_mode_id': mode.id if mode else False})
        dep.action_open()
        return dep

    def _order(self, dep, specs, partner=None):
        order = self.env['ta.order'].create({
            'partner_id': (partner or self.partner).id, 'departure_id': dep.id,
            'line_ids': [(0, 0, {'name': f'旅客{i}', 'kind': k})
                         for i, k in enumerate(specs)],
        })
        order.action_confirm()
        return order

    def _line_balance(self, move, code):
        line = move.line_ids.filtered(lambda l: l.account_id.code == code)
        return round(sum(line.mapped('credit')) - sum(line.mapped('debit')), 2)

    def test_gross_split_and_idempotent(self):
        dep = self._departure(self._route([('adult', 3000), ('child', 2000)]),
                              self.mode_gross)
        self._order(dep, ['adult', 'adult', 'child'])
        dep.action_confirm()
        dep.action_depart()  # 自动确认（配置开）
        rec = dep.recognition_ids
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec.mode, 'gross')
        self.assertAlmostEqual(rec.gross_amount, 8000.0)
        self.assertAlmostEqual(rec.net_amount, 7547.17, places=2)
        self.assertAlmostEqual(rec.tax_amount, 452.83, places=2)
        self.assertEqual(rec.move_id.state, 'posted')
        self.assertEqual(rec.move_id.date, dep.date_start)
        self.assertAlmostEqual(self._line_balance(rec.move_id, '600101'), 7547.17, places=2)
        self.assertAlmostEqual(self._line_balance(rec.move_id, '222101'), 452.83, places=2)
        dr = rec.move_id.line_ids.filtered(
            lambda l: l.account_id.id == self.recv_account.id
            and l.partner_id == self.partner)
        self.assertAlmostEqual(sum(dr.mapped('debit')), 8000.0)
        # 幂等：再次触发不新增
        dep.action_recognize_revenue()
        self.assertEqual(len(dep.recognition_ids), 1)

    def test_auto_off_manual_button(self):
        self.company.ta_revenue_auto_on_depart = False
        dep = self._departure(self._route([('adult', 3000)]), self.mode_gross)
        self._order(dep, ['adult'])
        dep.action_confirm()
        dep.action_depart()
        self.assertFalse(dep.recognition_ids)
        dep.action_recognize_revenue()
        self.assertEqual(len(dep.recognition_ids), 1)
        with self.assertRaises(UserError):
            self._departure(self._route([('adult', 3000)]),
                            self.mode_gross).action_recognize_revenue()  # 未发团拦截

    def test_vat_rate_zero(self):
        self.company.ta_vat_rate = 0.0
        dep = self._departure(self._route([('adult', 3000)]), self.mode_gross)
        self._order(dep, ['adult'])
        dep.action_confirm()
        dep.action_depart()
        rec = dep.recognition_ids
        self.assertAlmostEqual(rec.net_amount, 3000.0)
        self.assertAlmostEqual(rec.tax_amount, 0.0)

    def test_net_41_diff_no_split(self):
        dep = self._departure(self._route([('adult', 500)]), self.mode_dd)
        self._order(dep, ['adult', 'adult'])
        item = self.env['ta.dispatch.item'].create({
            'departure_id': dep.id, 'kind': 'ticket', 'supplier_id': self.partner.id,
            'name': '门票', 'qty': 1, 'unit_price': 800})
        item.action_confirm()
        dep.action_confirm()
        dep.action_depart()
        rec = dep.recognition_ids
        self.assertEqual(rec.mode, 'net')
        self.assertAlmostEqual(rec.gross_amount, 1000.0)
        self.assertAlmostEqual(rec.net_amount, 200.0)  # 差价 = 1000-800
        self.assertAlmostEqual(rec.tax_amount, 0.0)
        self.assertAlmostEqual(self._line_balance(rec.move_id, '600103'), 200.0)
        self.assertAlmostEqual(self._line_balance(rec.move_id, '224101'), -200.0)
        # 计调账单成本科目已分流到 224101
        self.assertEqual(item.move_id.invoice_line_ids.account_id.code, '224101')

    def test_net_41_diff_split_tax(self):
        self.company.ta_revenue_dd_split_tax = True
        dep = self._departure(self._route([('adult', 500)]), self.mode_dd)
        self._order(dep, ['adult', 'adult'])
        item = self.env['ta.dispatch.item'].create({
            'departure_id': dep.id, 'kind': 'ticket', 'supplier_id': self.partner.id,
            'name': '门票', 'qty': 1, 'unit_price': 800})
        item.action_confirm()
        dep.action_confirm()
        dep.action_depart()
        rec = dep.recognition_ids
        self.assertAlmostEqual(rec.net_amount, 188.68, places=2)
        self.assertAlmostEqual(rec.tax_amount, 11.32, places=2)
        self.assertAlmostEqual(self._line_balance(rec.move_id, '600103'), 188.68, places=2)
        self.assertAlmostEqual(self._line_balance(rec.move_id, '222101'), 11.32, places=2)

    def test_claim_then_recognize_net_zero(self):
        dep = self._departure(self._route([('adult', 3000)]), self.mode_gross)
        order = self._order(dep, ['adult'])
        dep.action_confirm()
        bank = self.env['ta.bank.line'].create({
            'amount': 3000.0, 'journal_id': self.bank_journal.id,
            'partner_name': '收入确认测试客户', 'ref': 'REV-1'})
        claim = self.env['ta.payment.claim'].with_user(self.u_sales).create({
            'line_ids': [(0, 0, {'bank_line_id': bank.id, 'amount': 3000.0})],
            'alloc_ids': [(0, 0, {'order_id': order.id, 'amount_allocated': 3000.0})]})
        claim.action_submit()
        claim.with_user(self.u_acct).action_approve()
        dep.action_depart()
        rec = dep.recognition_ids
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec.move_id.state, 'posted')
        # 客户应收科目（1122）：认领贷方 3000 + 确认借方 3000 → 净额 0
        balance = sum(self.env['account.move.line'].search([
            ('account_id', '=', self.recv_account.id),
            ('partner_id', '=', self.partner.id),
            ('parent_state', '=', 'posted'),
        ]).mapped(lambda l: l.debit - l.credit))
        self.assertAlmostEqual(balance, 0.0)

    def test_cancel_reverses_move(self):
        dep = self._departure(self._route([('adult', 3000)]), self.mode_gross)
        self._order(dep, ['adult'])
        dep.action_confirm()
        dep.action_depart()
        rec = dep.recognition_ids
        rec.with_user(self.u_mgr).action_cancel()
        self.assertEqual(rec.state, 'cancel')
        rev = self.env['account.move'].search(
            [('reversed_entry_id', '=', rec.move_id.id)], limit=1)
        self.assertTrue(rev)
        self.assertEqual(rev.state, 'posted')
        # 冲销后可重新确认
        dep.action_recognize_revenue()
        self.assertEqual(len(dep.recognition_ids.filtered(lambda r: r.state == 'posted')), 1)
