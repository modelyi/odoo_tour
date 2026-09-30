# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDispatchPaidHistoryPayable(TransactionCase):
    """批3-3 迁移口径（ta_dispatch 侧）：历史条目 move_id 空 + raw 直写 paid_date
    → ta.supplier.payable 视图按条目全额已付（paid_total 计入）。

    与 ta_finance/tests/test_supplier_payable.py::test_historical_paid_date_direct_write
    同口径（视图归属 ta_finance，本模块不新增依赖：模型未注册时跳过）。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['res.partner'].create({'name': '历史请款测试供应商'})
        route = cls.env['ta.route'].create({
            'name': '历史请款口径测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 1000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-12-01',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()

    def test_raw_paid_date_counts_full_in_payable(self):
        if 'ta.supplier.payable' not in self.env:
            self.skipTest('ta_finance 未安装，视图不可用')
        # 迁移脚本同款 raw INSERT（state=confirmed、move_id NULL、paid_date 有值）
        self.env.cr.execute(
            "INSERT INTO ta_dispatch_item (company_id, departure_id, route_id, supplier_id,"
            " kind, name, qty, unit_price, amount, state, move_id, paid_date, note,"
            " create_uid, write_uid, create_date, write_date)"
            " VALUES (%s, %s, %s, %s, 'ticket', '历史请款(迁移) QK-T', 1, 700, 700,"
            " 'confirmed', NULL, '2024-07-15', 'ETM|X|P900001',"
            " %s, %s, NOW(), NOW())",
            (self.env.company.id, self.dep.id, self.dep.route_id.id, self.supplier.id,
             self.env.uid, self.env.uid))
        item = self.env['ta.dispatch.item'].search(
            [('note', '=', 'ETM|X|P900001')], limit=1)
        self.assertTrue(item, 'raw 直建条目应可读回')
        self.assertEqual(item.paid_date, fields.Date.to_date('2024-07-15'))
        self.assertFalse(item.move_id)
        row = self.env['ta.supplier.payable'].search([
            ('departure_id', '=', self.dep.id),
            ('supplier_id', '=', self.supplier.id)])
        self.assertEqual(len(row), 1)
        row.invalidate_recordset()
        self.assertAlmostEqual(row.item_total, 700.0, places=2)
        self.assertAlmostEqual(row.bill_total, 0.0)
        self.assertAlmostEqual(row.paid_total, 700.0, places=2)   # 全额已付口径
        self.assertAlmostEqual(row.open_amount, 0.0, places=2)
        self.assertEqual(row.bill_state, 'none')
        self.assertEqual(row.kinds, 'ticket')
        # 反证：paid_date 置空 → paid_total 归 0（有值才是已付的接口语义）
        self.env.cr.execute(
            "UPDATE ta_dispatch_item SET paid_date = NULL WHERE id = %s", (item.id,))
        item.invalidate_recordset(['paid_date'])
        row.invalidate_recordset()
        self.assertAlmostEqual(row.paid_total, 0.0, places=2)
        self.assertAlmostEqual(row.open_amount, 700.0, places=2)
