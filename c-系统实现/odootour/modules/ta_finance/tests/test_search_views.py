# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReceivableAgingSearch(TransactionCase):
    """批4-B：应收账龄（SQL 视图）全文搜索。
    关键闸门：name_search 必须经 _rec_names_search 命中视图行。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': '搜索测试客户-AGING'})
        route = cls.env['ta.route'].create({
            'name': '搜索测试线路-AGING',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 1500})]})
        route.action_on_sale()
        dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-05',
            'seats_total': 10, 'seats_min': 2})
        dep.action_open()
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.partner.id, 'departure_id': dep.id,
            'line_ids': [(0, 0, {'name': '王五', 'kind': 'adult'})]})
        cls.order.action_confirm()
        cls.env.flush_all()  # SQL 视图同事务写入需先落盘

    def test_name_search_by_order_name(self):
        rows = self.env['ta.receivable.aging'].search(
            [('order_id', '=', self.order.id)])
        self.assertEqual(len(rows), 1, '确认订单应有且仅有一行账龄')
        res = self.env['ta.receivable.aging'].name_search(self.order.name)
        self.assertIn(rows.id, [r[0] for r in res],
                      '按订单号搜索应命中对应账龄行')
        match = [r for r in res if r[0] == rows.id]
        self.assertEqual(match[0][1], self.order.name,
                         '建议展示名应为订单号（_rec_name=order_name）')

    def test_claim_search_refs(self):
        """认领单 order_ids/partner_ids 按认领去向聚合（search view 依赖）。"""
        claim = self.env['ta.payment.claim'].create({
            'alloc_ids': [(0, 0, {'order_id': self.order.id,
                                  'amount_allocated': 500.0})]})
        self.assertEqual(claim.order_ids, self.order)
        self.assertEqual(claim.partner_ids, self.partner)


@tagged('post_install', '-at_install')
class TestListSearchViews(TransactionCase):
    """批4-B：银行流水 / 收款认领列表 search view 存在性（轻量 arch 断言）。"""

    def test_bank_line_search_view(self):
        view = self.env.ref('ta_finance.view_ta_bank_line_search',
                            raise_if_not_found=False)
        self.assertTrue(view)
        arch = view.arch_db
        for fname in ('date', 'ref', 'journal_id', 'partner_name',
                      'amount', 'state'):
            self.assertIn('name="%s"' % fname, arch)

    def test_payment_claim_search_view(self):
        view = self.env.ref('ta_finance.view_ta_payment_claim_search',
                            raise_if_not_found=False)
        self.assertTrue(view)
        arch = view.arch_db
        for fname in ('name', 'date', 'order_ids', 'partner_ids', 'state'):
            self.assertIn('name="%s"' % fname, arch)
