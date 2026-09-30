# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


def _get_or_create_account(env, code, name, account_type, **extra):
    """幂等取数（坑㊱：存量库 1002/2202 等已存在）：search by code 命中即用。"""
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
class TestSupplierPayable(TransactionCase):
    """批3-2 T2.1：确认条目→账单→过账→登记付款→视图 paid/open 联动；历史直写口径。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.expense_account = _get_or_create_account(
            cls.env, '6401', '主营业务成本-payable测试', 'expense_direct_cost')
        cls.company.expense_account_id = cls.expense_account.id
        cls.payable_account = _get_or_create_account(
            cls.env, '2202', '应付账款-payable测试', 'liability_payable')
        cls.bank_account = _get_or_create_account(
            cls.env, '1002', '银行存款-payable测试', 'asset_current')
        cls.supplier_a = cls.env['res.partner'].create({
            'name': '付款测试车队',
            'property_account_payable_id': cls.payable_account.id})
        cls.supplier_b = cls.env['res.partner'].create({
            'name': '付款测试酒店',
            'property_account_payable_id': cls.payable_account.id})
        cls.purchase_journal = _get_or_create_journal(
            cls.env, 'purchase', '采购测试-payable', 'PUCHP')
        cls.bank_journal = _get_or_create_journal(
            cls.env, 'bank', '银行测试-payable', 'BNKP',
            default_account_id=cls.bank_account.id)
        out_lines = cls.bank_journal.outbound_payment_method_line_ids
        if not out_lines:
            out_lines = cls.env['account.payment.method.line'].create({
                'name': 'Manual OUT: payable测试',
                'journal_id': cls.bank_journal.id,
                'payment_method_id': cls.env.ref(
                    'account.account_payment_method_manual_out').id,
                'payment_account_id': cls.bank_account.id,
            })
        cls.out_line = out_lines[:1]
        route = cls.env['ta.route'].create({
            'name': '付款闭环测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 1000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()

    def _item(self, supplier=None, kind='vehicle', price=500.0, qty=1.0):
        return self.env['ta.dispatch.item'].create({
            'departure_id': self.dep.id, 'kind': kind,
            'supplier_id': (supplier or self.supplier_a).id,
            'name': f'{kind}条目', 'qty': qty, 'unit_price': price})

    def _row(self, supplier):
        self.env.flush_all()
        rows = self.env['ta.supplier.payable'].search([
            ('departure_id', '=', self.dep.id),
            ('supplier_id', '=', supplier.id)])
        self.assertEqual(len(rows), 1, f'视图应有 {supplier.name} 一行')
        return rows

    def _pay(self, move, date, amount=None):
        vals = {
            'journal_id': self.bank_journal.id,
            'payment_method_line_id': self.out_line.id,
            'payment_date': date,
        }
        if amount is not None:
            vals['amount'] = amount
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids).create(vals)
        return wizard._create_payments()

    def test_bill_state_and_paid_flow(self):
        # T2.1 全付闭环：确认→草稿账单→过账→登记付款→字段与视图联动
        item = self._item(price=530.0, qty=2.0)  # 1060
        item.action_confirm()
        self.assertEqual(item.bill_state, 'draft')
        self.assertAlmostEqual(item.paid_amount, 0.0)
        self.assertFalse(item.paid_date)
        row = self._row(self.supplier_a)
        self.assertEqual(row.bill_state, 'draft')
        self.assertAlmostEqual(row.item_total, 1060.0)
        self.assertAlmostEqual(row.bill_total, 1060.0)
        self.assertAlmostEqual(row.paid_total, 0.0)
        self.assertAlmostEqual(row.open_amount, 1060.0)
        self.assertIn('vehicle', row.kinds)

        move = item.move_id
        move.action_post()
        item.invalidate_recordset(['bill_state', 'paid_amount', 'paid_date'])
        self.assertEqual(item.bill_state, 'posted')

        self._pay(move, '2026-11-05')
        item.invalidate_recordset(['bill_state', 'paid_amount', 'paid_date'])
        self.assertAlmostEqual(item.paid_amount, 1060.0, places=2)
        self.assertEqual(item.paid_date, fields.Date.to_date('2026-11-05'))
        row = self._row(self.supplier_a)
        self.assertAlmostEqual(row.paid_total, 1060.0, places=2)
        self.assertAlmostEqual(row.open_amount, 0.0, places=2)
        self.assertEqual(row.bill_state, 'posted')

    def test_partial_pay_and_granularity(self):
        # 团×供应商粒度 + 部分付款 + kinds 去重聚合
        i1 = self._item(supplier=self.supplier_a, price=500.0, qty=2.0)  # 1000
        i2 = self._item(supplier=self.supplier_a, kind='hotel', price=200.0)
        i3 = self._item(supplier=self.supplier_b, price=300.0)
        for it in (i1, i2, i3):
            it.action_confirm()
        i1.move_id.action_post()
        self._pay(i1.move_id, '2026-11-10', amount=400.0)  # 部分付款 400/1000
        i1.invalidate_recordset(['paid_amount'])
        self.assertAlmostEqual(i1.paid_amount, 400.0, places=2)
        row_a = self._row(self.supplier_a)
        self.assertAlmostEqual(row_a.item_total, 1200.0)
        self.assertAlmostEqual(row_a.bill_total, 1200.0)
        self.assertAlmostEqual(row_a.paid_total, 400.0, places=2)
        self.assertAlmostEqual(row_a.open_amount, 800.0, places=2)
        # 仍有草稿账单（i2）→ 汇总态取 draft
        self.assertEqual(row_a.bill_state, 'draft')
        self.assertEqual(row_a.kinds, 'hotel,vehicle')
        row_b = self._row(self.supplier_b)
        self.assertAlmostEqual(row_b.item_total, 300.0)
        self.assertAlmostEqual(row_b.paid_total, 0.0)

    def test_historical_paid_date_direct_write(self):
        # 批3-3 口径：无账单条目 raw SQL 直写 paid_date → 计入 paid_total
        item = self._item(supplier=self.supplier_a, price=800.0)
        item.action_confirm()
        item.move_id.unlink()  # 模拟历史条目（无供应商账单）
        item.invalidate_recordset(['move_id', 'bill_state'])
        self.env.flush_all()
        # 迁移脚本同款 raw SQL：证明列存在且可直写
        self.env.cr.execute(
            "UPDATE ta_dispatch_item SET paid_date = '2024-05-20' WHERE id = %s",
            (item.id,))
        item.invalidate_recordset(['paid_date', 'bill_state', 'paid_amount'])
        self.assertEqual(item.paid_date, fields.Date.to_date('2024-05-20'))
        self.assertEqual(item.bill_state, 'none')
        self.assertAlmostEqual(item.paid_amount, 0.0)  # 虚拟字段：无账单不取历史值
        row = self._row(self.supplier_a)
        self.assertAlmostEqual(row.item_total, 800.0)
        self.assertAlmostEqual(row.bill_total, 0.0)
        self.assertAlmostEqual(row.paid_total, 800.0, places=2)
        self.assertAlmostEqual(row.open_amount, 0.0, places=2)
        self.assertEqual(row.bill_state, 'none')
