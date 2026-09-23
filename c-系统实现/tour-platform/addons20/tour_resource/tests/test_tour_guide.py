# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestTourGuide(BaseCommon):

    # 20 的 BaseCommon 默认把用例跑在一个只有 base.group_user 的 Test User 上
    # （`base/tests/common.py:18 + _callSetUp`），不再是 admin。19 现网这些用例是
    # 以 admin 身份跑的，而 admin 在运营期被手工加进了 计调/导游管理/财务 组 ——
    # 所以空库 + 默认用户必然全是 AccessError，属夹具差异而非代码回归。
    # 旅行社经理 implied 了其余 tour 组；hr.group_hr_user 是 resource.resource/hr.employee
    # 的最小授权（20 里 resource.resource 的 crud 只给 Officer）。
    _test_user_groups = (
        'base.group_user',
        'tour_base.group_tour_manager',
        'hr.group_hr_user',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_guide = cls.env['res.partner'].create({
            'name': '张三（导游）',
        })
        cls.partner_external = cls.env['res.partner'].create({
            'name': '李四（外部导游）',
        })

    def _create_guide(self, **vals):
        defaults = {
            'name': '测试导游',
            'guide_code': 'GD%s' % self.env['tour.guide'].search_count([]),
        }
        defaults.update(vals)
        return self.env['tour.guide'].create(defaults)

    # ---------- partner_id 独立关联 ----------

    def test_partner_id_independent(self):
        """partner_id 是独立 Many2one，不依赖 employee_id"""
        guide = self._create_guide(partner_id=self.partner_guide.id)
        self.assertEqual(guide.partner_id, self.partner_guide)
        self.assertFalse(guide.employee_id)

    def test_external_guide_with_partner(self):
        """外部导游可以关联任意 partner，无需 employee"""
        guide = self._create_guide(
            name='李四',
            partner_id=self.partner_external.id,
        )
        self.assertEqual(guide.partner_id.name, '李四（外部导游）')
        self.assertFalse(guide.employee_id, '外部导游不应有员工档案')

    def test_onchange_partner_fills_name(self):
        """选择 partner 时自动带出姓名（仅 name 为空时）"""
        guide = self.env['tour.guide'].new({
            'guide_code': 'GD_NEW',
        })
        self.assertFalse(guide.name)
        guide.partner_id = self.partner_guide
        guide._onchange_partner_id()
        self.assertEqual(guide.name, '张三（导游）')

    def test_onchange_partner_no_overwrite(self):
        """name 已有值时不覆盖"""
        guide = self.env['tour.guide'].new({
            'name': '自定义名称',
            'guide_code': 'GD_X',
        })
        guide.partner_id = self.partner_guide
        guide._onchange_partner_id()
        self.assertEqual(guide.name, '自定义名称')

    # ---------- guide_code 唯一性 ----------

    def test_guide_code_unique(self):
        """导游证号全局唯一"""
        self._create_guide(guide_code='GD_UNIQUE')
        with self.assertRaises(Exception):
            self._create_guide(guide_code='GD_UNIQUE')

    # ---------- employee_id 1:1 约束 ----------

    def test_employee_unique(self):
        """同一员工不能关联多个导游"""
        employee = self.env['hr.employee'].create({'name': '员工A'})
        self._create_guide(employee_id=employee.id)
        with self.assertRaises(Exception):
            self._create_guide(employee_id=employee.id)

    # ---------- guide_star 范围校验 ----------

    def test_guide_star_valid(self):
        """星级 0~5 合法"""
        guide = self._create_guide(guide_star=4.5)
        self.assertEqual(guide.guide_star, 4.5)

    def test_guide_star_out_of_range(self):
        """星级超出 0~5 报错"""
        with self.assertRaises(ValidationError):
            self._create_guide(guide_star=6.0)

    def test_guide_star_negative(self):
        """星级负数报错"""
        with self.assertRaises(ValidationError):
            self._create_guide(guide_star=-1.0)

    # ---------- 审核通过逻辑 ----------

    def test_audit_approve_requires_id_num(self):
        """审核通过时身份证必填"""
        guide = self._create_guide(id_num=False)
        with self.assertRaises(ValidationError):
            guide.action_audit_approve()

    def test_audit_approve_success(self):
        """身份证已填，审核通过"""
        guide = self._create_guide(id_num='110101199001011234')
        guide.action_audit_approve()
        self.assertTrue(guide.audit_chk)
        self.assertTrue(guide.audit_user)
        self.assertTrue(guide.audit_date)

    # ---------- 智能按钮计数 ----------

    def test_loan_count_zero_when_no_model(self):
        """tour.guide.loan 模型不存在时计数为 0"""
        guide = self._create_guide()
        self.assertEqual(guide.loan_count, 0)

    def test_real_pay_count_zero_when_no_expenses(self):
        """无关联 hr.expense 记录时计数为 0"""
        guide = self._create_guide()
        self.assertEqual(guide.real_pay_count, 0)

    # ---------- 智能按钮计数：非 0 路径 ----------
    # 上面两条只走 "0 条记录" 分支：read_group 返回空列表时，参数顺序写错也一样得 0，
    # 等于没测。20 的 read_group 恰恰是"位置对调但不报错"的变更（TDS-30 §5.6 第 13 行），
    # 所以必须有非 0 且**每个导游数量不同**的用例，才能区分"分组键错位"。

    def _loan_model(self):
        if 'tour.guide.loan' not in self.env:
            self.skipTest('tour.guide.loan 由 tour_accounting/tour_guide_portal 提供，本库未装')
        return self.env['tour.guide.loan']

    def test_loan_count_per_guide(self):
        """A=3 / B=1 / C=0：分组计数按导游分别正确，不是全局总数"""
        Loan = self._loan_model()
        a = self._create_guide(name='甲')
        b = self._create_guide(name='乙')
        c = self._create_guide(name='丙')
        for _i in range(3):
            Loan.create({'guide_id': a.id, 'amount': 100.0})
        Loan.create({'guide_id': b.id, 'amount': 50.0})
        self.assertEqual(a.loan_count, 3)
        self.assertEqual(b.loan_count, 1)
        self.assertEqual(c.loan_count, 0)
        # 独立算法交叉核对（search_count 不走 read_group 代码路径）
        for guide in (a, b, c):
            self.assertEqual(
                guide.loan_count,
                Loan.search_count([('guide_id', '=', guide.id)]),
                '%s 的 loan_count 与 search_count 不一致' % guide.name)

    def test_evaluation_count_per_guide(self):
        """评价数同样按导游分组（tour.guide.evaluation 在 tour_operation）"""
        if 'tour.guide.evaluation' not in self.env:
            self.skipTest('tour.guide.evaluation 由 tour_operation 提供，本库未装')
        Eval = self.env['tour.guide.evaluation']
        a = self._create_guide(name='甲')
        b = self._create_guide(name='乙')
        Eval.create({'guide_id': a.id})
        Eval.create({'guide_id': a.id})
        Eval.create({'guide_id': b.id})
        self.assertEqual(a.evaluation_count, 2)
        self.assertEqual(b.evaluation_count, 1)
        self.assertEqual(b.evaluation_count,
                         Eval.search_count([('guide_id', '=', b.id)]))

    def test_real_pay_count_per_guide(self):
        """实付单计数（hr.expense.x_guide_id）也要走非 0 路径"""
        if 'hr.expense' not in self.env or 'x_guide_id' not in self.env['hr.expense']._fields:
            self.skipTest('hr.expense.x_guide_id 不在本库')
        Expense = self.env['hr.expense']
        a = self._create_guide(name='甲')
        b = self._create_guide(name='乙')
        for guide, n in ((a, 2), (b, 1)):
            for _i in range(n):
                Expense.create({'name': '报销', 'x_guide_id': guide.id,
                                'total_amount': 10.0, 'employee_id': self.env['hr.employee'].create(
                                    {'name': '员工%s%s' % (guide.name, _i)}).id})
        self.assertEqual(a.real_pay_count, 2)
        self.assertEqual(b.real_pay_count, 1)
        self.assertEqual(a.real_pay_count,
                         Expense.search_count([('x_guide_id', '=', a.id)]))

    # ---------- action_view_employee ----------

    def test_action_view_employee_no_employee(self):
        """无员工时跳转创建新员工"""
        guide = self._create_guide(name='王五')
        action = guide.action_view_employee()
        self.assertEqual(action['res_model'], 'hr.employee')
        self.assertEqual(action['view_mode'], 'form')
        self.assertNotIn('res_id', action)
        self.assertEqual(action['context']['default_name'], '王五')

    def test_action_view_employee_with_employee(self):
        """有员工时跳转已有记录"""
        employee = self.env['hr.employee'].create({'name': '已有员工'})
        guide = self._create_guide(employee_id=employee.id)
        action = guide.action_view_employee()
        self.assertEqual(action['res_id'], employee.id)
