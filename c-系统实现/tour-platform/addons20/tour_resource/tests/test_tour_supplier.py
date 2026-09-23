# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestTourSupplier(BaseCommon):

    # 见 test_tour_guide.py 同一处说明：20 的用例默认跑在只有 base.group_user 的
    # Test User 上，须自己声明业务身份（旅行社经理 implied 计调/财务/导游管理）。
    _test_user_groups = (
        'base.group_user',
        'tour_base.group_tour_manager',
        'hr.group_hr_user',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_hotel = cls.env['res.partner'].create({
            'name': '测试酒店公司',
        })

    def _create_supplier(self, **vals):
        defaults = {
            'name': '测试供应商',
            'sup_type': 'hotel',
        }
        defaults.update(vals)
        return self.env['tour.supplier'].create(defaults)

    # ---------- 基本创建 ----------

    def test_create_basic(self):
        supplier = self._create_supplier()
        self.assertEqual(supplier.name, '测试供应商')
        self.assertEqual(supplier.sup_type, 'hotel')
        self.assertTrue(supplier.active)

    def test_name_required(self):
        with self.assertRaises(Exception):
            self.env['tour.supplier'].create({'sup_type': 'hotel'})

    # ---------- partner_id 独立关联 ----------

    def test_partner_id_independent(self):
        supplier = self._create_supplier(partner_id=self.partner_hotel.id)
        self.assertEqual(supplier.partner_id, self.partner_hotel)

    def test_without_partner(self):
        supplier = self._create_supplier()
        self.assertFalse(supplier.partner_id)

    def test_onchange_partner_id_fills_name(self):
        supplier = self.env['tour.supplier'].new({
            'partner_id': self.partner_hotel.id,
        })
        supplier._onchange_partner_id()
        self.assertEqual(supplier.name, '测试酒店公司')

    def test_onchange_partner_id_no_overwrite(self):
        supplier = self.env['tour.supplier'].new({
            'name': '已有名称',
            'partner_id': self.partner_hotel.id,
        })
        supplier._onchange_partner_id()
        self.assertEqual(supplier.name, '已有名称')

    # ---------- sup_type ----------

    def test_sup_type_values(self):
        for code, _label in self.env['tour.supplier']._fields['sup_type'].selection:
            supplier = self._create_supplier(name='供应商_%s' % code, sup_type=code)
            self.assertEqual(supplier.sup_type, code)

    # ---------- 默认值 ----------

    def test_active_default(self):
        supplier = self._create_supplier()
        self.assertTrue(supplier.active)

    def test_company_id_default(self):
        supplier = self._create_supplier()
        self.assertEqual(supplier.company_id, self.env.company)

    # ---------- 审核 ----------

    def test_audit_approve(self):
        supplier = self._create_supplier()
        self.assertFalse(supplier.audit_chk)
        supplier.action_audit_approve()
        self.assertTrue(supplier.audit_chk)
        self.assertTrue(supplier.audit_user)
        self.assertTrue(supplier.audit_date)

    # ---------- 字段 CRUD ----------

    def test_field_values(self):
        supplier = self._create_supplier(
            et_cmp_code='ET001',
            help_code='CSGY',
            manager='张三',
            manager_mobile='13800138000',
            credit_lmt=100000.0,
            level_id='a',
            province='云南',
            city_name='昆明',
            bank='工商银行',
            account='测试账号',
            pay_way='月结',
        )
        self.assertEqual(supplier.et_cmp_code, 'ET001')
        self.assertEqual(supplier.help_code, 'CSGY')
        self.assertEqual(supplier.manager, '张三')
        self.assertEqual(supplier.credit_lmt, 100000.0)
        self.assertEqual(supplier.level_id, 'a')
        self.assertEqual(supplier.province, '云南')
        self.assertEqual(supplier.bank, '工商银行')

    # ---------- 跨模块约束 ----------

    def test_shop_agreement_constraint(self):
        shop = self._create_supplier(name='购物店C', sup_type='shop')
        hotel = self._create_supplier(name='酒店D', sup_type='hotel')

        agreement = self.env['tour.shop.agreement'].create({
            'shop_id': shop.id,
            'name': 'AGR001',
        })
        self.assertEqual(agreement.shop_id.sup_type, 'shop')

        with self.assertRaises(ValidationError):
            agreement.shop_id = hotel.id
