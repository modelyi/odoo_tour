# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from ..models.ta_route import strip_html


@tagged('post_install', '-at_install')
class TestRouteItinerary(TransactionCase):
    """T1.1 行程编排扩字段 + strip_html 工具。"""

    def test_stop_extended_fields(self):
        route = self.env['ta.route'].create({
            'name': '行程编排测试线',
            'stop_ids': [(0, 0, {
                'day_no': 1, 'name': '集合出发', 'title': '清晨出发',
                'city': '上海', 'traffic': '大巴',
                'meal_breakfast': '含', 'meal_lunch': '含', 'meal_dinner': None,
                'accommodation': '五星酒店', 'content': '详细行程说明',
                'meal': '早/中', 'note': 'ETM|LD|1',
            })],
        })
        stop = route.stop_ids
        self.assertEqual(stop.title, '清晨出发')
        self.assertEqual(stop.traffic, '大巴')
        self.assertEqual(stop.meal_breakfast, '含')
        self.assertEqual(stop.meal_lunch, '含')
        self.assertFalse(stop.meal_dinner)
        self.assertEqual(stop.accommodation, '五星酒店')
        self.assertEqual(stop.content, '详细行程说明')
        # 兼容：旧单栏 meal 不删不动，仍可写读
        self.assertEqual(stop.meal, '早/中')
        # 来源引用 note（copy=False）：创建与读取
        self.env['ta.route.stop'].create({
            'route_id': route.id, 'day_no': 2, 'name': '返程',
            'note': 'ETM|LD|2'})
        self.assertEqual(sorted(route.stop_ids.mapped('note')), ['ETM|LD|1', 'ETM|LD|2'])
        self.assertEqual(route.days, 2)

    def test_strip_html_basic(self):
        self.assertEqual(strip_html('<p>第一天&nbsp;游览<BR>外滩</p>'),
                         '第一天 游览\n外滩')
        self.assertEqual(strip_html('<div><span>甲</span><span>乙</span></div>'), '甲 乙')
        self.assertEqual(strip_html('<script>alert(1)</script>正文<style>x{}</style> end'),
                         '正文 end')
        self.assertEqual(strip_html('&lt;b&gt;粗体字面量&lt;/b&gt; &amp; 符号'),
                         '<b>粗体字面量</b> & 符号')

    def test_strip_html_empty(self):
        for v in (None, '', False, '   ', '<p></p>'):
            self.assertEqual(strip_html(v), '')
