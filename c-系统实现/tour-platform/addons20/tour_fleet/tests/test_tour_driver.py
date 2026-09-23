# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestTourDriver(BaseCommon):

    # 见 tour_resource/tests/test_tour_guide.py：20 的 BaseCommon 默认用只有
    # base.group_user 的 Test User 跑用例；旅行社经理 implied 导游管理/计调/财务，
    # hr.group_hr_user 供 hr.employee（→ resource.resource）创建。
    _test_user_groups = (
        'base.group_user',
        'tour_base.group_tour_manager',
        'hr.group_hr_user',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_driver = cls.env['res.partner'].create({
            'name': '王师傅（司机）',
        })
        cls.partner_external = cls.env['res.partner'].create({
            'name': '赵师傅（外部司机）',
        })

    def _create_driver(self, **vals):
        defaults = {
            'name': '测试司机',
        }
        defaults.update(vals)
        return self.env['tour.driver'].create(defaults)

    # ---------- partner_id 独立关联 ----------

    def test_partner_id_independent(self):
        """partner_id 是独立 Many2one，不依赖 employee_id"""
        driver = self._create_driver(partner_id=self.partner_driver.id)
        self.assertEqual(driver.partner_id, self.partner_driver)
        self.assertFalse(driver.employee_id)

    def test_external_driver_with_partner(self):
        """外部司机可以关联任意 partner，无需 employee"""
        driver = self._create_driver(
            name='赵师傅',
            partner_id=self.partner_external.id,
        )
        self.assertEqual(driver.partner_id.name, '赵师傅（外部司机）')
        self.assertFalse(driver.employee_id, '外部司机不应有员工档案')

    def test_onchange_partner_fills_name(self):
        """选择 partner 时自动带出姓名（仅 name 为空时）"""
        driver = self.env['tour.driver'].new({})
        self.assertFalse(driver.name)
        driver.partner_id = self.partner_driver
        driver._onchange_partner_id()
        self.assertEqual(driver.name, '王师傅（司机）')

    def test_onchange_partner_no_overwrite(self):
        """name 已有值时不覆盖"""
        driver = self.env['tour.driver'].new({
            'name': '自定义名称',
        })
        driver.partner_id = self.partner_driver
        driver._onchange_partner_id()
        self.assertEqual(driver.name, '自定义名称')

    # ---------- employee_id 1:1 约束 ----------

    def test_employee_unique(self):
        """同一员工不能关联多个司机"""
        employee = self.env['hr.employee'].create({'name': '司机员工A'})
        self._create_driver(employee_id=employee.id)
        with self.assertRaises(Exception):
            self._create_driver(employee_id=employee.id)

    # ---------- guide_id 关联 ----------

    def test_guide_link(self):
        """司机可关联导游（司机兼导游）"""
        guide = self.env['tour.guide'].create({
            'name': '导游兼司机',
            'guide_code': 'GD_DRIVER',
        })
        driver = self._create_driver(guide_id=guide.id)
        self.assertEqual(driver.guide_id, guide)

    # ---------- loan_rate 校验 ----------

    def test_loan_rate_valid(self):
        """借款利率正数合法"""
        driver = self._create_driver(loan_rate=5.5)
        self.assertEqual(driver.loan_rate, 5.5)

    def test_loan_rate_zero(self):
        """借款利率零合法"""
        driver = self._create_driver(loan_rate=0)
        self.assertEqual(driver.loan_rate, 0)

    def test_loan_rate_negative(self):
        """借款利率负数报错"""
        with self.assertRaises(ValidationError):
            self._create_driver(loan_rate=-1.0)

    # ---------- 基本字段 ----------

    def test_driver_fields(self):
        """司机基本字段可正常存取"""
        driver = self._create_driver(
            name='张师傅',
            driver_code='DRV001',
            sex='male',
            licence_type='A1',
            driver_licence='320102199001011234',
            mobile='13800138000',
        )
        self.assertEqual(driver.name, '张师傅')
        self.assertEqual(driver.driver_code, 'DRV001')
        self.assertEqual(driver.sex, 'male')
        self.assertEqual(driver.licence_type, 'A1')
        self.assertEqual(driver.driver_licence, '320102199001011234')
        self.assertEqual(driver.mobile, '13800138000')

    def test_active_default(self):
        """默认启用"""
        driver = self._create_driver()
        self.assertTrue(driver.active)

    def test_company_default(self):
        """默认当前公司"""
        driver = self._create_driver()
        self.assertEqual(driver.company_id, self.env.company)
