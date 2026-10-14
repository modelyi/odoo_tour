# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.route = cls.env['ta.route'].create({
            'name': '订单测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [
                (0, 0, {'kind': 'adult', 'amount': 3000}),
                (0, 0, {'kind': 'child', 'amount': 2000}),
                (0, 0, {'kind': 'single', 'amount': 500}),
            ],
        })
        cls.route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': cls.route.id, 'date_start': '2026-10-01',
            'seats_total': 5, 'seats_min': 2})
        cls.dep.action_open()

    def _mk_order(self, specs):
        return self.env['ta.order'].create({
            'kind': 'team', 'departure_id': self.dep.id,
            'line_ids': [(0, 0, {'name': f'旅客{i}', 'kind': k})
                         for i, k in enumerate(specs)],
        })

    def test_confirm_seats_and_plan(self):
        order = self._mk_order(['adult', 'adult', 'child'])
        order.action_confirm()
        self.assertEqual(order.state, 'confirmed')
        self.assertEqual(self.dep.seats_used, 3)
        self.assertEqual(order.amount_total, 8000)
        self.assertEqual(len(order.plan_ids), 1)
        self.assertEqual(order.plan_ids.amount, 8000)
        with self.assertRaises(UserError):
            order.action_confirm()  # 幂等：不能重复确认

    def test_cancel_releases_once(self):
        order = self._mk_order(['adult'])
        order.action_confirm()
        order.action_cancel()
        self.assertEqual(self.dep.seats_used, 0)
        self.assertEqual(order.amount_paid, 0)

    def test_over_capacity(self):
        order = self._mk_order(['adult'] * 6)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_settle_requires_full_payment(self):
        order = self._mk_order(['adult', 'adult'])
        order.action_confirm()
        order.action_trip()
        with self.assertRaises(UserError):
            order.action_settle()
        order._ta_apply_paid(6000)
        order.action_settle()
        self.assertEqual(order.state, 'settled')

    def test_apply_paid_bounds(self):
        order = self._mk_order(['adult'])
        order.action_confirm()
        with self.assertRaises(UserError):
            order._ta_apply_paid(3001)
        with self.assertRaises(UserError):
            order._ta_apply_paid(-1)

    def test_kind_change_refills_unit_price(self):
        # 批6 P1-8：改价别按价目表回填单价；未改价别时手工价保留
        order = self._mk_order(['adult'])
        line = order.line_ids
        self.assertAlmostEqual(line.unit_price, 3000.0)
        line.kind = 'child'
        self.assertAlmostEqual(line.unit_price, 2000.0)
        line.unit_price = 1800.0  # 手工改价
        self.assertAlmostEqual(line.unit_price, 1800.0)
        line.kind = 'single'
        self.assertAlmostEqual(line.unit_price, 500.0)
