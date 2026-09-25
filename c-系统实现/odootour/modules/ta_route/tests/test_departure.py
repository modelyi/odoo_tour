# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestDeparture(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.route = cls.env['ta.route'].create({
            'name': '班期测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 1000})],
        })
        cls.route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': cls.route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 5})
        cls.dep2 = cls.env['ta.departure'].create({
            'route_id': cls.route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 2})
        cls.manager = cls.env['res.users'].create({
            'name': 'mgr', 'login': 'mgr@test',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('ta_base.group_ta_manager').id])],
        })

    def test_full_state_machine(self):
        self.dep.action_open()
        self.dep.change_seats(6)
        self.assertEqual(self.dep.seats_free, 4)
        self.dep.action_confirm()
        self.dep.action_depart()
        self.dep.action_settle()
        self.assertEqual(self.dep.state, 'settled')

    def test_confirm_below_min_requires_manager(self):
        self.dep.action_open()
        self.dep.change_seats(3)
        with self.assertRaises(UserError):
            self.dep.action_confirm()
        with self.assertRaises(UserError):
            # 非管理层（普通计调）同样被拦
            self.dep.with_user(self.env['res.users'].create({
                'name': 'disp', 'login': 'disp@test',
                'group_ids': [(6, 0, [
                    self.env.ref('base.group_user').id,
                    self.env.ref('ta_base.group_ta_dispatcher').id])],
            })).action_confirm()
        self.dep.with_user(self.manager).action_confirm()
        self.assertEqual(self.dep.state, 'confirmed')

    def test_capacity_guard(self):
        self.dep.action_open()
        with self.assertRaises(UserError):
            self.dep.change_seats(11)
        self.dep.change_seats(4)
        with self.assertRaises(UserError):
            self.dep.change_seats(-5)
        self.assertEqual(self.dep.seats_used, 4)

    def test_cancel_blocked_with_bookings(self):
        self.dep.action_open()
        self.dep.change_seats(2)
        with self.assertRaises(UserError):
            self.dep.action_cancel()
        self.assertEqual(self.dep.state, 'open')

    def test_merge_moves_seats(self):
        self.dep.action_open()
        self.dep2.action_open()
        self.dep2.change_seats(3)
        wiz = self.env['ta.departure.merge'].create({
            'target_id': self.dep.id, 'source_ids': [(6, 0, self.dep2.ids)]})
        wiz.action_validate()
        self.assertEqual(self.dep.seats_used, 3)
        self.assertEqual(self.dep2.state, 'merged')
        self.assertEqual(self.dep2.merge_target_id, self.dep)
        self.assertEqual(self.dep2.seats_used, 0)
