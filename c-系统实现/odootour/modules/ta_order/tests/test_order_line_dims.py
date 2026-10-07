# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOrderLineDims(TransactionCase):
    """批5-迭代3（P1-1 AC-15）：报名名单客源地维度（性别/年龄段/客源地）
    字段读写、搜索/分组可用、报名名单视图透出。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        route = cls.env['ta.route'].create({
            'name': '名单维度测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-12-01',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.order = cls.env['ta.order'].create({
            'departure_id': cls.dep.id,
            'line_ids': [
                (0, 0, {'name': '张三', 'kind': 'adult', 'gender': 'male',
                        'age_group': 'middle', 'origin_province': '浙江'}),
                (0, 0, {'name': '李四', 'kind': 'adult', 'gender': 'female',
                        'age_group': 'senior', 'origin_province': '江苏'}),
            ]})

    def test_dimension_fields_read_write(self):
        line = self.order.line_ids.filtered(lambda l: l.name == '张三')
        self.assertEqual(line.gender, 'male')
        self.assertEqual(line.age_group, 'middle')
        self.assertEqual(line.origin_province, '浙江')
        line.write({'gender': 'female', 'age_group': 'youth',
                    'origin_province': '上海'})
        self.assertEqual(line.gender, 'female')
        self.assertEqual(line.age_group, 'youth')
        self.assertEqual(line.origin_province, '上海')

    def test_search_and_read_group(self):
        hits = self.env['ta.order.line'].search([('origin_province', '=', '江苏')])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits.name, '李四')
        groups = self.env['ta.order.line'].read_group(
            [('order_id', '=', self.order.id)], ['gender'], ['amount:sum'])
        self.assertEqual(len(groups), 2, '按性别分组应得两组')

    def test_view_exposes_dimension_fields(self):
        arch = self.env.ref('ta_order.view_ta_order_form').arch_db
        for fname in ('gender', 'age_group', 'origin_province'):
            self.assertIn('name="%s"' % fname, arch,
                          '报名名单树应透出 %s 字段' % fname)
