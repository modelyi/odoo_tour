# -*- coding: utf-8 -*-
"""tour.dashboard 的聚合口径核对（19→20 read_group 变更的回归网）。

三条被测路径都用了 20 新签名的 `_read_group`，且各自的**失败模式不同**：

* `_get_tour_states` —— groupby + `__count`，位置写反会把计数落到错的 state 上；
* `_get_pending_bookings` —— `dict(groups)` 直接把元组列表转映射；
* `_get_financial_pending` —— 只有 `amount:sum`、无 groupby（返回值 `[row]`，取 `[0][0]`），
  而且整段被 `try/except: pass` 包着：**取错位置不会报错，只会静默返回空列表**，
  所以这里必须断言"有草稿请款时列表非空"，只断言金额等于 0 是假绿。

用例都配了"不走 read_group 的独立算法"（search_count / 直接 sum）作交叉核对。
"""
from odoo.tests import tagged
from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestTourDashboard(BaseCommon):

    # 同 TestTourGuide：20 的 BaseCommon 用只含 base.group_user 的 Test User 跑用例。
    # 旅行社经理 implied 其余 tour 组。产品/项目的 manager 组是上游权限事实，不是我们
    # 放宽：tour.line 委托建 product.template（create 只给 group_product_manager），
    # 计划确认流程建 project.project（create 只给 group_project_manager）。
    # 现网这两个动作能做成，是因为账号被手工加进了管理员组 → 属 B2 迁移数据。
    _test_user_groups = (
        'base.group_user',
        'tour_base.group_tour_manager',
        'project.group_project_user',
        'project.group_project_manager',
        'product.group_product_manager',
        'hr.group_hr_user',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.line = cls.env['tour.line'].create({
            'name': '测试线路（看板）',
            'day_num': 3,
        })

    def _create_plan(self, code, state='draft', **vals):
        defaults = {
            'plan_code': code,
            'plan_name': '计划%s' % code,
            'line_id': self.line.id,
            'begin_date': '2026-01-10',
            'end_date': '2026-01-12',
            'state': state,
        }
        defaults.update(vals)
        return self.env['tour.plan'].create(defaults)

    # ---------- _get_tour_states ----------

    def test_dashboard_state_counts_are_per_state(self):
        """draft=3 / pending=2 不能被读成 draft=5 或全 0"""
        if 'tour.plan' not in self.env:
            self.skipTest('tour.plan 由 tour_order 提供，本库未装')
        for i in range(3):
            self._create_plan('TB_D%d' % i, 'draft')
        for i in range(2):
            self._create_plan('TB_P%d' % i, 'pending')

        rows = self.env['tour.dashboard']._get_tour_states()
        counts = {r['state']: r['count'] for r in rows}
        Plan = self.env['tour.plan']
        self.assertEqual(
            counts.get('draft'),
            Plan.search_count([('state', '=', 'draft')]),
            'draft 计数与 search_count 不一致：%s' % counts)
        self.assertEqual(
            counts.get('pending'),
            Plan.search_count([('state', '=', 'pending')]),
            'pending 计数与 search_count 不一致：%s' % counts)
        self.assertEqual(counts.get('draft'), 3)
        self.assertEqual(counts.get('pending'), 2)
        all_row = [r for r in rows if r['state'] == 'all']
        self.assertEqual(len(all_row), 1, '应有一行"全部活跃"')
        self.assertEqual(all_row[0]['count'], 5, '全部活跃 = 3 + 2，不是 0 也不是全表数')

    # ---------- _get_pending_bookings ----------

    def test_dashboard_booking_counts_by_resource_type(self):
        """resource_type 分组：guide=2 / vehicle=0（vehicle 无记录，不能串到 guide 头上）"""
        if 'project.task' not in self.env:
            self.skipTest('project 未装')
        # project_task._check_guide_audit 要求 guide_id.audit_chk，走真实审核动作而不是
        # 直接塞布尔位（审核动作本身还校验身份证）。
        guide = self.env['tour.guide'].create({
            'name': '看板导游', 'guide_code': 'GD_DASH',
            'id_num': '110101199001011234',
        })
        guide.action_audit_approve()
        project = self.env['project.project'].create({'name': '看板项目'})
        for i in range(2):
            self.env['project.task'].create({
                'name': '派团任务%d' % i,
                'project_id': project.id,
                'state': '01_in_progress',
                'resource_type': 'guide',
                'guide_id': guide.id,
            })

        rows = self.env['tour.dashboard']._get_pending_bookings()
        counts = {r['type']: r['count'] for r in rows}
        self.assertEqual(
            counts.get('guide'),
            self.env['project.task'].search_count([
                ('state', '=', '01_in_progress'), ('resource_type', '=', 'guide')]),
            'guide 计数与 search_count 不一致：%s' % counts)
        self.assertEqual(counts.get('guide'), 2)
        self.assertEqual(counts.get('vehicle'), 0)
        self.assertEqual(len(rows), 7, '七个资源类型都要出一行，缺项要显式给 0')

    # ---------- _get_financial_pending（静默失败高危） ----------

    def test_dashboard_pay_request_sum_not_swallowed(self):
        """草稿请款金额合计要出数；try/except 会吞掉取位错误 → 必须断言非空"""
        if 'tour.pay.request' not in self.env:
            self.skipTest('tour.pay.request 由 tour_accounting 提供，本库未装')
        if 'tour.plan' not in self.env:
            self.skipTest('tour.plan 未装')
        plan = self._create_plan('TB_PAY1', 'draft')
        PR = self.env['tour.pay.request']
        for amount in (100.0, 250.0):
            PR.create({'plan_id': plan.id, 'amount': amount})
        expected = sum(PR.search([('state', '=', 'draft')]).mapped('amount'))

        pending = self.env['tour.dashboard']._get_financial_pending()
        rows = pending['pay_requests']
        self.assertTrue(rows, '有草稿请款却返回空列表 = 聚合被 except 吞了')
        self.assertEqual(rows[0]['count'], 2)
        self.assertAlmostEqual(rows[0]['amount'], expected, places=2)
