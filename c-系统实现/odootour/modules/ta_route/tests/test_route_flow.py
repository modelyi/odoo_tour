# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestRouteFlow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.route = cls.env['ta.route'].create({
            'name': '测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})],
        })

    def test_sale_state_machine(self):
        self.assertEqual(self.route.state, 'draft')
        self.route.action_on_sale()
        self.assertEqual(self.route.state, 'on_sale')
        self.route.action_off()
        self.assertEqual(self.route.state, 'off')

    def test_on_sale_requires_price_and_stop(self):
        bare = self.env['ta.route'].create({'name': '空线路'})
        with self.assertRaises(UserError):
            bare.action_on_sale()

    def test_off_blocked_by_open_departure(self):
        self.route.action_on_sale()
        dep = self.env['ta.departure'].create({
            'route_id': self.route.id, 'date_start': '2026-10-01', 'seats_total': 20})
        dep.action_open()
        with self.assertRaises(UserError):
            self.route.action_off()

    def test_list_price_min_adult(self):
        self.env['ta.route.price'].create({'route_id': self.route.id, 'kind': 'adult', 'amount': 2800})
        self.assertEqual(self.route.list_price, 2800)
