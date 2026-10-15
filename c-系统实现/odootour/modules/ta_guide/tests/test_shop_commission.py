# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, AccessError

from odoo.addons.ta_guide.models.ta_guide_commission import _calc_labor_tax


@tagged('post_install', '-at_install')
class TestShopCommission(TransactionCase):
    """批4-C：BS-08 购物返佣链路——购物记录/协议阶梯/司陪导协议（奖金+税务类型）
    → 佣金单生成（幂等）→ 确认（个税记录）→ 结算 → 退单重算 → 绩效联动。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # 恢复库带入全局生效人均线/算法配置会覆盖分成档与人均口径 → 测试内屏蔽
        cls.env['ta.per.capita.line'].search(
            [('state', '=', 'active')]).write({'state': 'inactive'})
        cls.env['ta.per.capita.calc'].search(
            [('state', '=', 'active')]).write({'state': 'inactive'})
        route = cls.env['ta.route'].create({
            'name': '购物测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '购物导游'})
        cls.u_guide = cls.env['res.users'].create({
            'name': '购物导游', 'login': 'shopg_t@test.local',
            'company_id': cls.company.id, 'partner_id': cls.guide.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_guide').id])]})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计S', 'login': 'acct_s@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})
        # 批5-迭代1：佣金确认/冲抵凭证需要杂项日记账（BS-08 §4.10）
        cls.gen_journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.gen_journal:
            cls.gen_journal = cls.env['account.journal'].create({
                'name': '杂项日记账S', 'code': 'GENS',
                'type': 'general', 'company_id': cls.company.id})
        cls.dep.guide_ids = [(6, 0, [cls.u_guide.id])]

        cls.customer = cls.env['res.partner'].create({'name': '购物客户'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.customer.id, 'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()  # heads=2

        cls.shop_partner = cls.env['res.partner'].create(
            {'name': '翡翠购物店', 'supplier_rank': 1})
        cls.agreement = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 15.0,
            'tier_rule_ids': [
                (0, 0, {'min_per_capita': 0.0, 'max_per_capita': 1000.0,
                        'commission_rate': 20.0}),
                (0, 0, {'min_per_capita': 1000.0, 'max_per_capita': 5000.0,
                        'commission_rate': 25.0}),
                (0, 0, {'min_per_capita': 5000.0, 'commission_rate': 30.0}),
            ]})
        cls.agreement.action_active()

        cls.staff_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': cls.guide.id,
            'tax_type': 'labor', 'id_number': '****1234',
            'share_rate': 40.0,
            'premium_rule_ids': [
                (0, 0, {'min_per_capita': 2500.0, 'premium_amount': 300.0}),
                (0, 0, {'min_per_capita': 5000.0, 'premium_amount': 500.0}),
            ]})
        cls.staff_agr.action_active()

    def _shop(self, amount=10000.0, guest_count=2):
        return self.env['ta.shop'].create({
            'departure_id': self.dep.id,
            'shop_partner_id': self.shop_partner.id,
            'shop_date': '2026-11-02',
            'guest_count': guest_count,
            'total_amount': amount,
            'guide_id': self.guide.id,
        })

    def _commissions(self):
        return self.env['ta.guide.commission'].search([
            ('departure_id', '=', self.dep.id),
            ('shop_partner_id', '=', self.shop_partner.id),
        ])

    def test_shop_constraints(self):
        with self.assertRaises(UserError):
            self._shop(amount=0.0)          # 金额必须 > 0
        with self.assertRaises(UserError):
            self._shop(guest_count=0)       # 客人数必须 > 0
        with self.assertRaises(UserError):
            self._shop(guest_count=3)       # 客人数 ≤ 团队人数（2）

    def test_agreement_tier_rate(self):
        agr = self.agreement
        self.assertAlmostEqual(agr._get_rate(500.0, '2026-06-01'), 20.0)
        self.assertAlmostEqual(agr._get_rate(2500.0, '2026-06-01'), 25.0)
        self.assertAlmostEqual(agr._get_rate(8000.0, '2026-06-01'), 30.0)
        self.assertAlmostEqual(agr._get_rate(500.0, '2027-01-01'), 0.0)  # 超有效期
        agr2 = self.env['ta.shop.agreement'].create({
            'shop_partner_id': self.shop_partner.id,
            'begin_date': '2027-01-01', 'end_date': '2027-12-31',
            'base_rate': 10.0})
        self.assertAlmostEqual(agr2._get_rate(500.0, '2027-06-01'), 0.0)  # 未生效

    def test_commission_generation(self):
        shop = self._shop(10000.0, 2)
        self.assertAlmostEqual(shop.per_capita, 5000.0)
        shop.with_user(self.u_acct).action_confirm()
        self.assertEqual(shop.state, 'confirmed')
        c = self._commissions()
        self.assertEqual(len(c), 1)
        self.assertEqual(c.state, 'draft')
        self.assertAlmostEqual(c.shop_amount, 10000.0)
        self.assertEqual(c.guest_count, 2)
        self.assertAlmostEqual(c.per_capita, 5000.0)
        self.assertAlmostEqual(c.commission_rate, 30.0)       # 阶梯：人均 5000 档
        self.assertAlmostEqual(c.commission_total, 3000.0)
        self.assertAlmostEqual(c.guide_share_rate, 40.0)
        self.assertAlmostEqual(c.guide_share_before_tax, 1200.0)
        self.assertAlmostEqual(c.premium, 500.0)              # 人均 5000 ≥ 5000 档
        self.assertAlmostEqual(c.allowance, 1700.0)
        self.assertAlmostEqual(c.guide_tax, 180.0)            # (1700-800)×20%
        self.assertAlmostEqual(c.tax_amount, 180.0)
        self.assertAlmostEqual(c.net_amount, 1520.0)
        self.assertAlmostEqual(c.company_retain, 1300.0)
        self.assertIn('返佣 30.0%', c.rule_note)

    def test_generation_grouped_and_idempotent(self):
        s1 = self._shop(6000.0, 2)
        s1.with_user(self.u_acct).action_confirm()
        c = self._commissions()
        self.assertEqual(len(c), 1)
        self.assertAlmostEqual(c.shop_amount, 6000.0)
        s2 = self._shop(4000.0, 2)
        s2.with_user(self.u_acct).action_confirm()
        self.assertEqual(len(c), 1)  # 同分组 upsert，不重复建单（NFR-2）
        self.assertAlmostEqual(c.shop_amount, 10000.0)
        self.assertEqual(c.state, 'draft')

    def test_no_agreement_no_commission(self):
        other = self.env['res.partner'].create({'name': '无协议店', 'supplier_rank': 1})
        shop = self.env['ta.shop'].create({
            'departure_id': self.dep.id, 'shop_partner_id': other.id,
            'shop_date': '2026-11-02', 'guest_count': 2,
            'total_amount': 1000.0, 'guide_id': self.guide.id})
        shop.with_user(self.u_acct).action_confirm()
        self.assertFalse(self.env['ta.guide.commission'].search([
            ('departure_id', '=', self.dep.id),
            ('shop_partner_id', '=', other.id)]))

    def test_labor_tax_brackets(self):
        # BS-08 §11 五档示例
        self.assertAlmostEqual(_calc_labor_tax(500.0), 0.0)
        self.assertAlmostEqual(_calc_labor_tax(3000.0), 440.0)
        self.assertAlmostEqual(_calc_labor_tax(10000.0), 1600.0)
        self.assertAlmostEqual(_calc_labor_tax(50000.0), 10000.0)
        self.assertAlmostEqual(_calc_labor_tax(105000.0), 26600.0)

    def test_salary_tax_type_no_withhold(self):
        self.staff_agr.tax_type = 'salary'
        shop = self._shop(10000.0, 2)
        shop.with_user(self.u_acct).action_confirm()
        c = self._commissions()
        self.assertEqual(c.guide_tax_type, 'salary')
        self.assertAlmostEqual(c.guide_tax, 0.0)  # 工资薪金并入月度综合所得，单笔不预扣
        self.assertAlmostEqual(c.net_amount, 1700.0)
        self.assertIn('月度综合所得', c.rule_note)

    def test_state_flow_and_tax_record(self):
        shop = self._shop()
        with self.assertRaises(AccessError):          # 导游不能确认购物（职务分离）
            shop.with_user(self.u_guide).action_confirm()
        shop.with_user(self.u_acct).action_confirm()
        c = self._commissions()
        with self.assertRaises(AccessError):          # 导游不能确认佣金
            c.with_user(self.u_guide).action_confirm()
        with self.assertRaises(UserError):            # 未确认不能结算
            c.with_user(self.u_acct).action_settle()
        c.with_user(self.u_acct).action_confirm()
        self.assertEqual(c.state, 'confirmed')
        self.assertTrue(c.confirm_uid)
        self.assertTrue(c.confirm_date)
        with self.assertRaises(UserError):            # 重复确认被拦
            c.with_user(self.u_acct).action_confirm()
        rec = c.tax_record_ids                       # AC-10 个税记录自动生成
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec.staff_id, self.guide)
        self.assertEqual(rec.tax_type, 'labor')
        self.assertEqual(rec.id_number, '****1234')
        self.assertAlmostEqual(rec.income_before_tax, 1700.0)
        self.assertAlmostEqual(rec.tax_amount, 180.0)
        self.assertAlmostEqual(rec.net_pay, 1520.0)
        self.assertEqual(rec.declare_state, 'undeclared')
        self.assertEqual(len(rec.declare_month), 7)
        rec.action_declare()
        self.assertEqual(rec.declare_state, 'declared')
        self.assertTrue(rec.declare_date)
        c.with_user(self.u_acct).action_settle()
        self.assertEqual(c.state, 'settled')
        self.assertAlmostEqual(c.payable_rest, 1520.0)
        with self.assertRaises(UserError):            # 结算幂等（NFR-2）
            c.with_user(self.u_acct).action_settle()

    def test_return_recompute(self):
        s1 = self._shop(6000.0, 2)
        s1.with_user(self.u_acct).action_confirm()
        s2 = self._shop(4000.0, 2)
        s2.with_user(self.u_acct).action_confirm()
        c = self._commissions()
        self.assertEqual(len(c), 1)
        self.assertAlmostEqual(c.shop_amount, 10000.0)
        with self.assertRaises(UserError):            # 退单原因必填
            s1.with_user(self.u_acct).action_return()
        with self.assertRaises(AccessError):          # 导游不能退单
            s1.with_user(self.u_guide).action_return()
        s1.return_reason = '游客退货'                 # 会计在表单填写原因后提交
        s1.with_user(self.u_acct).action_return()
        self.assertEqual(s1.state, 'returned')
        self.assertTrue(s1.return_date)
        self.assertTrue(s1.return_reason)
        cs = self._commissions()
        self.assertEqual(len(cs), 2)                  # 旧单取消 + 按剩余记录重算
        new_c = cs.filtered(lambda x: x.state == 'draft')
        self.assertEqual(len(new_c), 1)
        self.assertAlmostEqual(new_c.shop_amount, 4000.0)
        # 人均 4000/2=2000 → 阶梯 25% → 佣金总额 1000；分成 400；奖金 0（<2500）；税 0（≤800）
        self.assertAlmostEqual(new_c.per_capita, 2000.0)
        self.assertAlmostEqual(new_c.commission_total, 1000.0)
        self.assertAlmostEqual(new_c.guide_share_before_tax, 400.0)
        self.assertAlmostEqual(new_c.premium, 0.0)
        self.assertAlmostEqual(new_c.guide_tax, 0.0)
        self.assertAlmostEqual(new_c.net_amount, 400.0)

    def test_return_blocked_when_commission_confirmed(self):
        s1 = self._shop(6000.0, 2)
        s1.with_user(self.u_acct).action_confirm()
        c = self._commissions()
        c.with_user(self.u_acct).action_confirm()
        with self.assertRaises(UserError):            # 佣金已确认 → 提示红字/个税抵扣
            s1.with_user(self.u_acct).action_return()
        self.assertEqual(s1.state, 'confirmed')

    def test_performance_linkage(self):
        shop = self._shop(10000.0, 2)
        shop.with_user(self.u_acct).action_confirm()
        c = self._commissions()
        c.with_user(self.u_acct).action_confirm()
        c.with_user(self.u_acct).action_settle()
        self.env.flush_all()
        rows = self.env['ta.guide.performance'].search([
            ('guide_id', '=', self.guide.id), ('ym', '=', '2026-11')])
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows.commission_net, 1520.0)  # 税后净额联动绩效
