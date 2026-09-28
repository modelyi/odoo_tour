# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


def _get_or_create_account(env, code, name, account_type, **extra):
    """幂等取数（范式同 scripts/seed_ta_demo.py）：search by code 命中即用。"""
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
class TestScenicContribution(TransactionCase):
    """迭代5 T5.1：景点毛利贡献 = 团毛利 × 该景点门票成本 ÷ 全团成本（手算核对）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.expense_account = _get_or_create_account(
            cls.env, '6402', '主营业务成本S', 'expense_direct_cost')
        cls.env.company.expense_account_id = cls.expense_account.id
        cls.payable_account = _get_or_create_account(
            cls.env, '2203', '应付账款S', 'liability_payable')
        cls.purchase_journal = _get_or_create_journal(
            cls.env, 'purchase', '采购测试S', 'PUCHS')
        cls.s_ticket = cls.env['res.partner'].create({
            'name': '票务代订S', 'supplier_rank': 1,
            'property_account_payable_id': cls.payable_account.id})
        cls.s_scenic = cls.env['res.partner'].create({
            'name': '景区S', 'supplier_rank': 1,
            'property_account_payable_id': cls.payable_account.id})
        cls.s_hotel = cls.env['res.partner'].create({
            'name': '酒店S', 'supplier_rank': 1,
            'property_account_payable_id': cls.payable_account.id})
        route = cls.env['ta.route'].create({
            'name': '景点贡献线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        order = cls.env['ta.order'].create({
            'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'})]})
        order.action_confirm()
        order._ta_apply_paid(3000.0)  # 收入 3000

        def item(kind, supplier, price):
            it = cls.env['ta.dispatch.item'].create({
                'departure_id': cls.dep.id, 'kind': kind,
                'supplier_id': supplier.id, 'name': kind, 'qty': 1,
                'unit_price': price})
            it.action_confirm()
            return it
        # 全团成本 = 300 + 200 + 500 = 1000；毛利 = 3000 - 1000 = 2000
        item('ticket', cls.s_ticket, 300.0)
        item('scenic', cls.s_scenic, 100.0)
        item('scenic', cls.s_scenic, 100.0)   # 同景点两条 → 归并 200
        item('hotel', cls.s_hotel, 500.0)

    def test_contribution_split(self):
        rows = self.env['ta.scenic.contribution'].search(
            [('departure_id', '=', self.dep.id)])
        self.assertEqual(len(rows), 2, '仅 ticket/scenic 供应商成行')
        t = rows.filtered(lambda r: r.supplier_id == self.s_ticket)
        s = rows.filtered(lambda r: r.supplier_id == self.s_scenic)
        self.assertAlmostEqual(t.ticket_cost, 300.0)
        self.assertAlmostEqual(s.ticket_cost, 200.0)
        self.assertAlmostEqual(t.profit, 2000.0)
        self.assertAlmostEqual(t.cost_ratio, 30.0)
        self.assertAlmostEqual(s.cost_ratio, 20.0)
        self.assertAlmostEqual(t.profit_contribution, 600.0)  # 2000×300/1000
        self.assertAlmostEqual(s.profit_contribution, 400.0)  # 2000×200/1000
        self.assertAlmostEqual(
            sum(rows.mapped('profit_contribution')), 1000.0,
            msg='酒店不参与归因，贡献合计=毛利×(门票+景区)/全团成本')
