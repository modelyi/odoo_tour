# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTeamPnlSearch(TransactionCase):
    """批4-B：单团损益（SQL 视图）全文搜索。
    关键闸门：name_search 必须经 _rec_names_search 命中视图行，
    不能返回空/异常（SQL 视图 + display_name 搜索链路）。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        route = cls.env['ta.route'].create({
            'name': '搜索测试线路-PNL',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-05',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.env.flush_all()  # SQL 视图同事务写入需先落盘

    def test_name_search_by_code(self):
        res = self.env['ta.team.pnl'].name_search(self.dep.code)
        self.assertEqual([r[0] for r in res], [self.dep.id],
                         '按计划号搜索应命中对应损益行')
        self.assertEqual(res[0][1], self.dep.code,
                         '建议展示名应为计划号（_rec_name=code）')

    def test_name_search_by_route_name(self):
        res = self.env['ta.team.pnl'].name_search('搜索测试线路-PNL')
        self.assertIn(self.dep.id, [r[0] for r in res],
                      '按线路名搜索应命中对应损益行')

    def test_search_view_exists(self):
        view = self.env.ref('ta_dispatch.view_ta_team_pnl_search',
                            raise_if_not_found=False)
        self.assertTrue(view)
        arch = view.arch_db
        for fname in ('code', 'route_name', 'date_start', 'state'):
            self.assertIn('name="%s"' % fname, arch)
