# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


def _get_or_create_account(env, code, name, account_type, **extra):
    """幂等取数（范式同 test_supplier_payable）：search by code 命中即用。"""
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        vals = {'code': code, 'name': name, 'account_type': account_type}
        vals.update(extra)
        acc = env['account.account'].create(vals)
    return acc


@tagged('post_install', '-at_install')
class TestPaymentMethodAccountDefense(TransactionCase):
    """批4-A：付款方式行缺 payment_account_id 时日记账/付款两级自动回填防御。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.expense_account = _get_or_create_account(
            cls.env, '6401', '主营业务成本-批4A', 'expense_direct_cost')
        cls.company.expense_account_id = cls.expense_account.id
        cls.payable_account = _get_or_create_account(
            cls.env, '2202', '应付账款-批4A', 'liability_payable')
        cls.bank_account = _get_or_create_account(
            cls.env, '1002', '银行存款-批4A', 'asset_current')
        cls.supplier = cls.env['res.partner'].create({
            'name': '批4A付款测试供应商',
            'property_account_payable_id': cls.payable_account.id})
        cls.purchase_journal = cls.env['account.journal'].search(
            [('type', '=', 'purchase'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.purchase_journal:
            cls.purchase_journal = cls.env['account.journal'].create({
                'name': '采购测试-批4A', 'code': 'PU4A', 'type': 'purchase',
                'company_id': cls.company.id})

    def _new_bank_journal(self, code):
        return self.env['account.journal'].create({
            'name': '银行测试-批4A', 'code': code, 'type': 'bank',
            'company_id': self.company.id,
            'default_account_id': self.bank_account.id})

    def _new_outbound_line_without_account(self, journal):
        """直建方式行、不给过渡科目 → 模拟存量缺陷行（绕开日记账级防御）。"""
        return self.env['account.payment.method.line'].create({
            'name': '手动付款(无过渡科目)-批4A',
            'journal_id': journal.id,
            'payment_method_id': self.env.ref(
                'account.account_payment_method_manual_out').id,
        })

    def _posted_bill(self, amount=1060.0):
        """走计调条目原生路径造一张已过账供应商账单。"""
        route = self.env['ta.route'].create({
            'name': '批4A付款测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 1000})]})
        route.action_on_sale()
        dep = self.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'seats_total': 10, 'seats_min': 2})
        dep.action_open()
        item = self.env['ta.dispatch.item'].create({
            'departure_id': dep.id, 'kind': 'vehicle',
            'supplier_id': self.supplier.id, 'name': '车辆条目-批4A',
            'qty': 1.0, 'unit_price': amount})
        item.action_confirm()
        move = item.move_id
        move.action_post()
        return item, move

    def test_journal_create_backfills_payment_account(self):
        journal = self._new_bank_journal('B4A1')
        lines = journal.inbound_payment_method_line_ids \
            + journal.outbound_payment_method_line_ids
        self.assertTrue(lines, 'bank 日记账应自动带出收/付款方式行')
        for line in lines:
            self.assertEqual(line.payment_account_id, self.bank_account,
                             '缺过渡科目的方式行应自动回填 default_account_id')

    def test_journal_write_backfills_payment_account(self):
        journal = self._new_bank_journal('B4A2')
        lines = journal.inbound_payment_method_line_ids \
            + journal.outbound_payment_method_line_ids
        lines.write({'payment_account_id': False})
        self.assertFalse(any(l.payment_account_id for l in lines))
        journal.write({'name': '银行测试-批4A(改)'})
        for line in lines:
            self.assertEqual(line.payment_account_id, self.bank_account,
                             'journal.write 后应再次回填过渡科目')

    def test_payment_backfills_line_and_creates_move(self):
        journal = self._new_bank_journal('B4A3')
        line = self._new_outbound_line_without_account(journal)
        self.assertFalse(line.payment_account_id)
        item, move = self._posted_bill()
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create({
                'journal_id': journal.id,
                'payment_method_line_id': line.id,
                'payment_date': '2026-11-05',
            })
        payments = wizard._create_payments()
        self.assertEqual(len(payments), 1, '应生成一条付款')
        line.invalidate_recordset(['payment_account_id'])
        self.assertEqual(line.payment_account_id, self.bank_account,
                         '创建付款时应自动回填方式行过渡科目')
        pay = payments
        self.assertTrue(pay.move_id, '付款应生成凭证')
        self.assertIn(pay.state, ('paid', 'reconciled'),
                      '付款应为已支付（全额核销后为已核销）')
        self.assertEqual(
            self.env['account.move'].search_count(
                [('origin_payment_id', '=', pay.id)]), 1,
            '付款凭证（account.move）应存在')
        move.invalidate_recordset(['amount_residual'])
        self.assertAlmostEqual(move.amount_residual, 0.0, places=2,
                               msg='账单余额应被付款清偿')
        item.invalidate_recordset(['paid_amount'])
        self.assertAlmostEqual(item.paid_amount, 1060.0, places=2,
                               msg='条目已付款额应为全额')

    def test_payment_raises_when_no_default_account(self):
        journal = self._new_bank_journal('B4A4')
        # Odoo 20 核心 create 会自动补建 default_account_id → 模拟存量无默认科目
        # journal 需显式置空（该字段非 required，可写 False）
        journal.default_account_id = False
        self.assertFalse(journal.default_account_id)
        line = self._new_outbound_line_without_account(journal)
        self.assertFalse(line.payment_account_id)
        with self.assertRaises(UserError):
            self.env['account.payment'].create({
                'journal_id': journal.id,
                'payment_method_line_id': line.id,
                'amount': 100.0,
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'date': '2026-11-05',
            })
