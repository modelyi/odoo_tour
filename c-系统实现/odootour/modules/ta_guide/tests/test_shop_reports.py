# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


def _get_or_create_journal(env, jtype, name, code, **extra):
    """幂等日记账：先按测试专属 code 找，再按类型找存量，都没有才建。"""
    J = env['account.journal']
    comp = env.company.id
    j = J.search([('code', '=', code), ('company_id', '=', comp)], limit=1) \
        or J.search([('type', '=', jtype), ('company_id', '=', comp)], limit=1)
    if not j:
        vals = {'name': name, 'code': code, 'type': jtype, 'company_id': comp}
        vals.update(extra)
        j = J.create(vals)
    return j


@tagged('post_install', '-at_install')
class TestShopReports(TransactionCase):
    """批5-迭代3（P1-1）：购物对账 [4316]（AC-13）+ 多维度购物分析 [4307][4308][4309-4311]
    （AC-15）——1 团 2 客（不同性别/年龄/客源地）+ 购物 + 佣金确认后校验两个 SQL 视图。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # 佣金确认凭证需要杂项日记账（BS-08 §4.10）
        cls.gen_journal = _get_or_create_journal(
            cls.env, 'general', '杂项日记账RPT', 'GENRPT')

        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        route = cls.env['ta.route'].create({
            'name': '购物报表测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '报表导游'})
        cls.u_guide = cls.env['res.users'].create({
            'name': '报表导游', 'login': 'rpt_guide@test.local',
            'company_id': cls.company.id, 'partner_id': cls.guide.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_guide').id])]})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计RPT', 'login': 'rpt_acct@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})
        cls.dep.guide_ids = [(6, 0, [cls.u_guide.id])]

        cls.customer = cls.env['res.partner'].create({'name': '报表组团社'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.customer.id, 'departure_id': cls.dep.id,
            'line_ids': [
                (0, 0, {'name': '甲', 'kind': 'adult', 'gender': 'male',
                        'age_group': 'youth', 'origin_province': '浙江'}),
                (0, 0, {'name': '乙', 'kind': 'adult', 'gender': 'female',
                        'age_group': 'middle', 'origin_province': '江苏'}),
            ]})
        cls.order.action_confirm()  # heads=2

        cls.shop_partner = cls.env['res.partner'].create(
            {'name': '水晶购物店', 'supplier_rank': 1})
        cls.agreement = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 20.0})
        cls.agreement.action_active()
        cls.staff_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': cls.guide.id,
            'tax_type': 'labor', 'id_number': '****9012',
            'share_rate': 40.0})
        cls.staff_agr.action_active()

        shop = cls.env['ta.shop'].create({
            'departure_id': cls.dep.id,
            'shop_partner_id': cls.shop_partner.id,
            'shop_date': '2026-11-02',
            'guest_count': 2,
            'total_amount': 10000.0,
            'guide_id': cls.guide.id,
        })
        shop.with_user(cls.u_acct).action_confirm()
        cls.commission = cls.env['ta.guide.commission'].search([
            ('departure_id', '=', cls.dep.id),
            ('shop_partner_id', '=', cls.shop_partner.id),
        ], limit=1)
        cls.commission.with_user(cls.u_acct).action_confirm()
        cls.env.flush_all()  # SQL 视图同事务写入需先落盘

    def test_reconciliation(self):
        """购物对账：应付佣金/销项税/司陪分成/留存/笔数/日期，已付佣金=0。"""
        rows = self.env['ta.shop.reconciliation'].search([
            ('shop_partner_id', '=', self.shop_partner.id)])
        self.assertEqual(len(rows), 1, '购物对账应按购物店聚合成一行')
        row = rows
        self.assertEqual(row.shop_name, '水晶购物店')
        # 人均 5000 → 基础比例 20% → 佣金总额 2000；分成 40% → 800；留存 1200
        self.assertAlmostEqual(row.commission_payable, 2000.0)
        self.assertAlmostEqual(row.commission_tax, 0.0)
        self.assertAlmostEqual(row.staff_share, 800.0)
        self.assertAlmostEqual(row.company_retain, 1200.0)
        self.assertEqual(row.commission_count, 1)
        self.assertEqual(row.last_commission_date.strftime('%Y-%m-%d'), '2026-11-02')
        self.assertAlmostEqual(row.paid_total, 0.0, '已付佣金固定为 0（AC-17 未接入）')
        # 名称搜索（_rec_names_search）
        hit = self.env['ta.shop.reconciliation'].name_search('水晶购物店')
        self.assertIn(row.id, [r[0] for r in hit])

    def test_analysis_est_amount(self):
        """多维度分析：行数 = 名单行×购物组；est_amount = 人均购物 × 客人数。"""
        rows = self.env['ta.shop.analysis'].search([('departure_id', '=', self.dep.id)])
        self.assertEqual(len(rows), 2, '2 名客人应各出一行')
        male = rows.filtered(lambda r: r.gender == 'male')
        female = rows.filtered(lambda r: r.gender == 'female')
        self.assertEqual(len(male), 1)
        self.assertEqual(len(female), 1)
        self.assertEqual(male.age_group, 'youth')
        self.assertEqual(male.origin_province, '浙江')
        self.assertEqual(male.partner_id, self.customer)
        self.assertEqual(male.route_name, '购物报表测试线路')
        # 人均 = 10000 ÷ 2（加权前团队人数）= 5000；每行 1 人 → est_amount = 5000
        self.assertAlmostEqual(male.est_amount, 5000.0)
        self.assertAlmostEqual(female.est_amount, 5000.0)
        self.assertAlmostEqual(sum(rows.mapped('est_amount')), 10000.0)

    def test_analysis_read_group(self):
        """按性别/客源地分组汇总可读（pivot 依赖 read_group）。"""
        by_gender = self.env['ta.shop.analysis'].read_group(
            [('departure_id', '=', self.dep.id)], ['gender'], ['est_amount:sum'])
        self.assertEqual(len(by_gender), 2)
        amounts = {g[0]: g[1] for g in by_gender}
        self.assertAlmostEqual(amounts['male'], 5000.0)
        self.assertAlmostEqual(amounts['female'], 5000.0)
        by_origin = self.env['ta.shop.analysis'].read_group(
            [('departure_id', '=', self.dep.id)], ['origin_province'], ['est_amount:sum'])
        self.assertEqual(len(by_origin), 2)
