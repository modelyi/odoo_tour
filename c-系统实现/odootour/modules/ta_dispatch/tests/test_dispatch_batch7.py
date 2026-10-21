# -*- coding: utf-8 -*-
"""批7（BS-03 计调补齐）单测：

- 资源冲突检测（US-03-07）：同供应商跨团日期重叠拦截 / 异日放行 / ICP 关闭放行；
- 类型明细回填（BS-03 §3.1）：酒店房型×晚数×房价、餐次桌数、景区票种；
- completed 状态机 + 发团结算联动 + 成本口径仍含 completed；
- 营运中心二次确认（US-03-08）状态流转；
- 计调成本分析视图（US-03-09）口径；
- 发团计调进度看板（US-03-01）。
"""
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError
from odoo import fields

from .test_dispatch import _get_or_create_account, _get_or_create_journal


@tagged('post_install', '-at_install')
class TestDispatchBatch7(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.expense_account = _get_or_create_account(
            cls.env, '6401', '主营业务成本-dispatch测试', 'expense_direct_cost')
        cls.env.company.expense_account_id = cls.expense_account.id
        cls.payable_account = _get_or_create_account(
            cls.env, '2202', '应付账款-dispatch测试', 'liability_payable')
        cls.supplier = cls.env['res.partner'].create({
            'name': '批7测试车队',
            'property_account_payable_id': cls.payable_account.id})
        cls.guide = cls.env['res.partner'].create({
            'name': '批7测试导游',
            'property_account_payable_id': cls.payable_account.id})
        cls.purchase_journal = _get_or_create_journal(
            cls.env, 'purchase', '采购测试-dispatch7', 'PUCH7')
        route = cls.env['ta.route'].create({
            'name': '批7计调测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.route = route
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 20, 'seats_min': 0})
        cls.dep.action_open()

    def _dep(self, start='2026-11-01', end='2026-11-03'):
        dep = self.env['ta.departure'].create({
            'route_id': self.route.id, 'date_start': start, 'date_end': end,
            'seats_total': 10, 'seats_min': 0})
        dep.action_open()
        return dep

    def _item(self, dep=None, kind='vehicle', supplier=None, bare=False, **kw):
        vals = {
            'departure_id': (dep or self.dep).id, 'kind': kind,
            'supplier_id': (supplier or self.supplier).id,
            'name': kw.pop('name', '测试条目')}
        # bare=True：不传 qty/unit_price，交给 editable compute 依明细回填
        # （create 显式值会跳过计算，与 paid_date 同语义）
        if not bare:
            vals.setdefault('qty', 1.0)
            vals.setdefault('unit_price', 100.0)
        vals.update(kw)
        return self.env['ta.dispatch.item'].create(vals)

    # ---- US-03-07 冲突检测 ----
    def test_conflict_guide_same_day_blocked(self):
        dep2 = self._dep()
        a = self._item(kind='guide', supplier=self.guide, name='一团导游')
        a.action_confirm()
        b = self._item(dep=dep2, kind='guide', supplier=self.guide, name='二团导游')
        with self.assertRaises(UserError):
            b.action_confirm()
        self.assertEqual(b.state, 'draft')  # 拦截后不产生账单、状态不变

    def test_conflict_guide_different_day_passes(self):
        dep2 = self._dep(start='2026-11-05', end='2026-11-07')
        a = self._item(kind='guide', supplier=self.guide, name='一团导游')
        a.action_confirm()
        b = self._item(dep=dep2, kind='guide', supplier=self.guide, name='二团导游')
        b.action_confirm()
        self.assertEqual(b.state, 'confirmed')

    def test_conflict_icp_off_passes(self):
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_bool('ta_dispatch.conflict_check', False)
        try:
            dep2 = self._dep()
            a = self._item(kind='guide', supplier=self.guide, name='一团导游')
            a.action_confirm()
            b = self._item(dep=dep2, kind='guide', supplier=self.guide, name='二团导游')
            b.action_confirm()
            self.assertEqual(b.state, 'confirmed')
        finally:
            icc = self.env['ir.config_parameter'].sudo().search(
                [('key', '=', 'ta_dispatch.conflict_check')])
            icc.unlink()

    def test_conflict_same_departure_not_blocked(self):
        # 同团多条同供应商条目（不同日期）不受限
        a = self._item(kind='guide', supplier=self.guide, name='D1导游')
        a.action_confirm()
        b = self._item(kind='guide', supplier=self.guide, name='D3导游')
        b.action_confirm()

    # ---- BS-03 §3.1 类型明细回填 ----
    # 说明：qty/unit_price 为 editable compute（store+readonly=False），create 时
    # 显式提供值会跳过计算（"手工值优先"，与 paid_date 同语义）→ 明细回填用例
    # 不传 qty/unit_price，靠 compute 依明细赋值；真实 UI 中改明细字段亦触发回填。
    def test_hotel_detail_backfill(self):
        # 创建后写明细字段 → write 触发存储型 compute 重算回填（与 UI 表单一致）
        item = self._item(bare=True, kind='hotel', name='两晚三间')
        item.write({'room_price': 300.0, 'room_standard': 2, 'room_single': 1})
        self.assertEqual(item.night_num, 2)      # 11-01 → 11-03
        self.assertEqual(item.qty, 3.0)           # 2标 + 1单
        self.assertAlmostEqual(item.unit_price, 600.0)  # 300 × 2晚
        self.assertAlmostEqual(item.amount, 1800.0)
        # 手工改数量不被覆盖（明细不变时）
        item.qty = 2.5
        self.assertAlmostEqual(item.amount, 1500.0)

    def test_meal_detail_backfill(self):
        item = self._item(bare=True, kind='meal', name='正餐')
        item.write({'meal_type': 'lunch', 'table_count': 4, 'price_per_table': 600.0})
        self.assertEqual(item.qty, 4.0)
        self.assertAlmostEqual(item.unit_price, 600.0)
        self.assertAlmostEqual(item.amount, 2400.0)

    def test_scenic_ticket_backfill(self):
        item = self._item(bare=True, kind='scenic', name='门票', unit_price=120.0)
        item.write({'ticket_adult': 30, 'ticket_child': 20})
        self.assertEqual(item.qty, 50.0)
        self.assertAlmostEqual(item.amount, 6000.0)

    def test_date_end_guest_count_defaults(self):
        item = self._item()
        self.assertEqual(item.date_end, item.departure_id.date_end)
        self.assertEqual(item.guest_count, item.departure_id.seats_used)

    # ---- completed 状态机 + 结算联动 + 成本口径 ----
    def test_complete_and_settle_hook(self):
        a = self._item(name='大巴')
        a.action_confirm()
        a.action_complete()
        self.assertEqual(a.state, 'completed')
        # 已完成不可再确认（幂等方向）
        with self.assertRaises(UserError):
            a.action_complete()
        b = self._item(name='地接')
        b.action_confirm()
        # 发团流转：open → confirmed → departed → settled（settle 钩子自动完成）
        self.dep.action_confirm()
        self.dep.action_depart()
        self.dep.action_settle()
        self.assertEqual(b.state, 'completed')
        self.dep.invalidate_recordset()
        # 成本口径含 completed（批7 全仓库对齐）
        self.assertAlmostEqual(self.dep.dispatch_cost_total, 200.0)

    def test_completed_keeps_bill_and_blocks_cancel(self):
        # completed 条目取消应沿用既有防护：账单已生成（草稿）→ 取消会删账单；
        # 已过账账单仍拒绝取消（沿用原 action_cancel 逻辑）
        item = self._item(name='大巴')
        item.action_confirm()
        item.action_complete()
        item.move_id.action_post()
        with self.assertRaises(UserError):
            item.action_cancel()

    # ---- US-03-08 二次确认 ----
    def test_booking_confirm_flow(self):
        hotel = self._item(kind='hotel', name='酒店', room_price=100.0)
        hotel.action_confirm()
        self.assertEqual(hotel.confirm_state, 'unconfirmed')
        hotel.action_confirm_booking()
        self.assertEqual(hotel.confirm_state, 'confirmed')
        # 非酒店/景区不允许操作
        car = self._item(kind='vehicle', name='车')
        with self.assertRaises(UserError):
            car.action_confirm_booking()

    # ---- US-03-01 进度看板 ----
    def test_departure_progress(self):
        a = self._item(name='大巴')
        b = self._item(name='地接')
        a.action_confirm()
        self.dep.invalidate_recordset()
        self.assertEqual(self.dep.dispatch_active_count, 2)
        self.assertEqual(self.dep.dispatch_done_count, 1)
        self.assertAlmostEqual(self.dep.dispatch_completion_rate, 50.0)
        # 两条目均为车队（vehicle）：确认/总数 = 1/2
        self.assertIn('车队1/2', self.dep.dispatch_kind_summary)

    # ---- US-03-09 成本分析视图 ----
    def test_dispatch_summary_view(self):
        dep2 = self._dep(start='2026-11-05', end='2026-11-07')
        a = self._item(name='确认条目')
        a.action_confirm()
        b = self._item(name='取消条目')
        b.action_cancel()
        c = self._item(dep=dep2, kind='guide', supplier=self.guide, name='导游条目')
        c.action_confirm()
        self.env.flush_all()
        rows = self.env['ta.dispatch.summary'].search(
            [('company_id', '=', self.env.company.id)])
        vehicle_row = rows.filtered(
            lambda r: r.supplier_id == self.supplier and r.kind == 'vehicle')
        self.assertEqual(len(vehicle_row), 1)
        self.assertEqual(vehicle_row.item_count, 2)
        self.assertEqual(vehicle_row.confirmed_count, 1)
        self.assertEqual(vehicle_row.cancelled_count, 1)
        self.assertAlmostEqual(vehicle_row.amount_total, 100.0)
        self.assertAlmostEqual(vehicle_row.confirm_rate, 50.0)
        self.assertEqual(vehicle_row.month, '2026-11')
        guide_row = rows.filtered(
            lambda r: r.supplier_id == self.guide and r.kind == 'guide')
        self.assertEqual(len(guide_row), 1)
        self.assertAlmostEqual(guide_row.amount_total, 100.0)
        # 草稿账单不计入账单口径（bill_total 仅 posted）
        self.assertAlmostEqual(vehicle_row.bill_total, 0.0)
        self.assertAlmostEqual(vehicle_row.paid_total, 0.0)
