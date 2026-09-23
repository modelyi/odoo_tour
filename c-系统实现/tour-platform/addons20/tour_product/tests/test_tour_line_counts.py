# -*- coding: utf-8 -*-
"""tour.line 上两个智能按钮计数的回归网。

19 的 `read_group(domain, ['line_id'], ['line_id'])` 返回 `[{'line_id': (id, name),
'line_id_count': n}]`；20 的 `_read_group(domain, ['line_id'], ['__count'])` 返回
`[(recordset, n)]`。位置参数一换就变成"不报错但取不到数"（恒为 0），所以这里用
**两条线路、数量不同**的数据来钉住分组口径。见 TDS-30 §5.6 第 13 行。
"""
from odoo.tests import tagged
from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestTourLineCounts(BaseCommon):

    # 20 的 BaseCommon 用只含 base.group_user 的 Test User 跑用例（TDS-30 §5.6 #12）。
    # product.group_product_manager 不是我们放宽的权限，而是 19/20 上游的既有事实：
    # tour.line 经 `_inherits` 委托建 product.template，而上游只把 product.template 的
    # create 给 group_product_manager（19 `access_product_template_user` = 只读、
    # 20 唯一无组 ir_access 行是 product.product_comp_rule 记录规则）。
    # 现网能新增线路，是因为经理账号被手工加进了产品管理员组 —— 属 B2 迁移数据。
    _test_user_groups = (
        'base.group_user',
        'tour_base.group_tour_manager',
        'product.group_product_manager',
    )

    def _line(self, name):
        return self.env['tour.line'].create({'name': name, 'day_num': 2})

    def test_departure_and_detail_counts_per_line(self):
        line_a = self._line('线路A')
        line_b = self._line('线路B')
        line_c = self._line('线路C')
        Departure = self.env['tour.departure']
        Detail = self.env['tour.line.detail']
        for i in range(3):
            Departure.create({'line_id': line_a.id,
                              'start_date': '2026-03-0%d' % (i + 1)})
        Departure.create({'line_id': line_b.id, 'start_date': '2026-04-01'})
        for i in range(2):
            Detail.create({'line_id': line_a.id, 'day_no': i + 1})

        self.assertEqual(line_a.departure_count, 3)
        self.assertEqual(line_b.departure_count, 1)
        self.assertEqual(line_c.departure_count, 0)
        self.assertEqual(line_a.detail_count, 2)
        self.assertEqual(line_b.detail_count, 0)
        # 独立算法交叉核对
        self.assertEqual(line_a.departure_count,
                         Departure.search_count([('line_id', '=', line_a.id)]))
        self.assertEqual(line_a.detail_count,
                         Detail.search_count([('line_id', '=', line_a.id)]))

    def test_counts_refresh_after_write(self):
        """分组计数不是"装载时算一次"：新增/删除后必须跟着变"""
        line = self._line('线路D')
        departure = self.env['tour.departure'].create(
            {'line_id': line.id, 'start_date': '2026-05-01'})
        self.assertEqual(line.departure_count, 1)
        self.env['tour.departure'].create(
            {'line_id': line.id, 'start_date': '2026-05-02'})
        self.env['tour.line'].invalidate_model(['departure_count'])
        self.assertEqual(line.departure_count, 2)
        departure.unlink()
        self.env['tour.line'].invalidate_model(['departure_count'])
        self.assertEqual(line.departure_count, 1)
