# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestTourGuide(BaseCommon):

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

    def test_real_pay_count_zero_when_no_model(self):
        """tour.guide.real.pay 模型不存在时计数为 0"""
        guide = self._create_guide()
        self.assertEqual(guide.real_pay_count, 0)

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
