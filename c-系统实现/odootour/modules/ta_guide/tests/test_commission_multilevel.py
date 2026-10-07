# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.ta_guide.models.ta_guide_shop import _kind_weight


@tagged('post_install', '-at_install')
class TestMultilevelCommission(TransactionCase):
    """批5-迭代2：P1-2 多层分成引擎（BS-08 §3.2）+ P1-3 人均线/算法配置化（§4.7/§4.8）。

    基准数据：返佣协议固定 30%（无阶梯）；导游 40% 劳务（奖金 人均≥5000 → 500）、
    司机 10% 工资薪金、陪同 5% 劳务；发团挂司机/陪同；团队 2 成人（heads=2）。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.gen_journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.gen_journal:
            cls.gen_journal = cls.env['account.journal'].create({
                'name': '杂项日记账M', 'code': 'GENM',
                'type': 'general', 'company_id': cls.company.id})
        cls.env['ir.config_parameter'].sudo().set_float('ta_base.default_tax_rate', 0.06)

        route = cls.env['ta.route'].create({
            'name': '多层分成测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        cls.route = route
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 20, 'seats_min': 2})
        cls.dep.action_open()
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '多层导游'})
        cls.driver = cls.env['res.partner'].create({'name': '多层司机'})
        cls.escort = cls.env['res.partner'].create({'name': '多层陪同'})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计M', 'login': 'acct_m@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})
        cls.dep.driver_id = cls.driver.id
        cls.dep.escort_id = cls.escort.id

        cls.customer = cls.env['res.partner'].create({'name': '多层客户'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.customer.id, 'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()  # heads=2

        cls.shop_partner = cls.env['res.partner'].create(
            {'name': '多层购物店', 'supplier_rank': 1})
        cls.agreement = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 30.0})   # 固定 30%，无阶梯
        cls.agreement.action_active()

        cls.guide_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': cls.guide.id,
            'tax_type': 'labor', 'id_number': '****0001',
            'share_rate': 40.0,
            'premium_rule_ids': [
                (0, 0, {'min_per_capita': 5000.0, 'premium_amount': 500.0}),
            ]})
        cls.guide_agr.action_active()
        cls.driver_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'driver', 'staff_id': cls.driver.id,
            'tax_type': 'salary', 'id_number': '****0002',
            'share_rate': 10.0})
        cls.driver_agr.action_active()
        cls.escort_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'escort', 'staff_id': cls.escort.id,
            'tax_type': 'labor', 'id_number': '****0003',
            'share_rate': 5.0})
        cls.escort_agr.action_active()

    # ---- 辅助 ----
    def _shop(self, amount=10000.0, guest_count=2, partner=None):
        partner = partner or self.shop_partner
        return self.env['ta.shop'].create({
            'departure_id': self.dep.id,
            'shop_partner_id': partner.id,
            'shop_date': '2026-11-02',
            'guest_count': guest_count,
            'total_amount': amount,
            'guide_id': self.guide.id,
        })

    def _shop_partner(self, name):
        """独立购物店 + 固定 30% 返佣协议（隔离人均线各档场景）。"""
        partner = self.env['res.partner'].create({'name': name, 'supplier_rank': 1})
        agr = self.env['ta.shop.agreement'].create({
            'shop_partner_id': partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 30.0})
        agr.action_active()
        return partner

    def _commission(self, partner=None):
        return self.env['ta.guide.commission'].search([
            ('departure_id', '=', self.dep.id),
            ('shop_partner_id', '=', (partner or self.shop_partner).id),
        ])

    def _upsert(self, shop):
        """生产链路：购物记录确认 → 引擎按分组幂等生成/重算草稿佣金单。"""
        if shop.state == 'draft':
            shop.with_user(self.u_acct).action_confirm()
        return self.env['ta.guide.commission']._upsert_from_shop_group(shop)

    # ---- ① 多层分成：三协议 → 三行分成，金额/个税/实发/留存正确 ----
    def test_multilevel_rows_and_totals(self):
        shop = self._shop(10000.0, 2)
        shop.with_user(self.u_acct).action_confirm()
        c = self._commission()
        self.assertEqual(c.state, 'draft')
        rows = c.staff_line_ids.sorted('staff_type')
        self.assertEqual([r.staff_type for r in rows], ['driver', 'escort', 'guide'])
        # 导游 40% 劳务：分成 1200 + 奖金 500 → 个税 (1700-800)×20%=180 → 实发 1520
        g = rows.filtered(lambda r: r.staff_type == 'guide')
        self.assertEqual(g.staff_id, self.guide)
        self.assertAlmostEqual(g.share_rate, 40.0)
        self.assertAlmostEqual(g.share_before_tax, 1200.0)
        self.assertAlmostEqual(g.premium, 500.0)
        self.assertEqual(g.tax_type, 'labor')
        self.assertAlmostEqual(g.tax_amount, 180.0)
        self.assertAlmostEqual(g.net_pay, 1520.0)
        # 司机 10% 工资薪金：单笔不预扣
        d = rows.filtered(lambda r: r.staff_type == 'driver')
        self.assertEqual(d.staff_id, self.driver)
        self.assertAlmostEqual(d.share_before_tax, 300.0)
        self.assertAlmostEqual(d.premium, 0.0)
        self.assertEqual(d.tax_type, 'salary')
        self.assertAlmostEqual(d.tax_amount, 0.0)
        self.assertAlmostEqual(d.net_pay, 300.0)
        # 陪同 5% 劳务：150 ≤ 800 不预扣
        e = rows.filtered(lambda r: r.staff_type == 'escort')
        self.assertEqual(e.staff_id, self.escort)
        self.assertAlmostEqual(e.share_before_tax, 150.0)
        self.assertAlmostEqual(e.tax_amount, 0.0)
        self.assertAlmostEqual(e.net_pay, 150.0)
        # 主单汇总：allowance=Σgross、tax=Σ税、net=Σ实发、留存=佣金总额−Σgross（§3.2）
        self.assertAlmostEqual(c.allowance, 2150.0)
        self.assertAlmostEqual(c.tax_amount, 180.0)
        self.assertAlmostEqual(c.net_amount, 1970.0)
        self.assertAlmostEqual(c.company_retain, 850.0)   # 3000 − 2150
        # guide_* 兼容字段 = 导游行（向后兼容）
        self.assertAlmostEqual(c.guide_share_rate, 40.0)
        self.assertAlmostEqual(c.guide_share_before_tax, 1200.0)
        self.assertAlmostEqual(c.premium, 500.0)
        self.assertEqual(c.guide_tax_type, 'labor')
        self.assertAlmostEqual(c.guide_tax, 180.0)
        self.assertIn('司机分成 10.0%', c.rule_note)
        self.assertIn('陪同分成 5.0%', c.rule_note)

    # ---- ② 无协议人员不生成分成行 ----
    def test_no_agreement_no_row(self):
        shop = self._shop(10000.0, 2)
        shop.with_user(self.u_acct).action_confirm()
        c = self._commission()
        self.assertEqual(len(c.staff_line_ids), 3)
        self.dep.driver_id = False   # 发团不再挂司机
        self._upsert(shop)
        rows = c.staff_line_ids.sorted('staff_type')
        self.assertEqual([r.staff_type for r in rows], ['escort', 'guide'])
        self.assertAlmostEqual(c.allowance, 1850.0)   # 1700 + 150
        self.assertAlmostEqual(c.company_retain, 1150.0)

    # ---- ③ 个税代扣记录按分成行逐人生成（3 条） ----
    def test_tax_records_per_staff(self):
        shop = self._shop(10000.0, 2)
        shop.with_user(self.u_acct).action_confirm()
        c = self._commission()
        c.with_user(self.u_acct).action_confirm()
        self.assertEqual(c.state, 'confirmed')
        recs = c.tax_record_ids
        self.assertEqual(len(recs), 3)
        by_staff = {r.staff_id: r for r in recs}
        g = by_staff[self.guide]
        self.assertEqual(g.tax_type, 'labor')
        self.assertEqual(g.id_number, '****0001')
        self.assertAlmostEqual(g.income_before_tax, 1700.0)
        self.assertAlmostEqual(g.tax_amount, 180.0)
        self.assertAlmostEqual(g.net_pay, 1520.0)
        d = by_staff[self.driver]
        self.assertEqual(d.tax_type, 'salary')     # 司机工资薪金
        self.assertAlmostEqual(d.income_before_tax, 300.0)
        self.assertAlmostEqual(d.tax_amount, 0.0)
        self.assertAlmostEqual(d.net_pay, 300.0)
        e = by_staff[self.escort]
        self.assertAlmostEqual(e.income_before_tax, 150.0)
        self.assertAlmostEqual(e.tax_amount, 0.0)
        self.assertAlmostEqual(e.net_pay, 150.0)

    # ---- ④ 确认凭证：6407/2241/222102 按人拆行，行数 3+3×3，借贷平衡 ----
    def test_confirm_move_split_by_staff(self):
        shop = self._shop(10000.0, 2)
        shop.with_user(self.u_acct).action_confirm()
        c = self._commission()
        c.with_user(self.u_acct).action_confirm()
        move = c.move_id.with_user(self.u_acct)
        self.assertTrue(move)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(len(move.line_ids), 12)   # 1222/6051/222101 + 每人 3 行
        by_code = {}
        for line in move.line_ids:
            by_code.setdefault(line.account_id.code, line)
        self.assertAlmostEqual(by_code['1222'].debit, 3000.0)
        self.assertAlmostEqual(by_code['6051'].credit, 2830.19)
        self.assertAlmostEqual(by_code['222101'].credit, 169.81)
        costs = move.line_ids.filtered(lambda l: l.account_id.code == '6407')
        self.assertEqual(len(costs), 3)
        self.assertEqual(set(costs.mapped('debit')), {1700.0, 300.0, 150.0})
        self.assertEqual(costs.mapped('partner_id'),
                         self.guide | self.driver | self.escort)
        payables = move.line_ids.filtered(lambda l: l.account_id.code == '2241')
        self.assertEqual(len(payables), 3)
        self.assertEqual(set(payables.mapped('credit')), {1520.0, 300.0, 150.0})
        self.assertEqual(payables.mapped('partner_id'),
                         self.guide | self.driver | self.escort)
        wh_taxes = move.line_ids.filtered(lambda l: l.account_id.code == '222102')
        self.assertEqual(len(wh_taxes), 3)
        self.assertEqual(set(wh_taxes.mapped('credit')), {180.0, 0.0})
        # 借贷平衡（NFR-1）
        self.assertAlmostEqual(
            sum(move.line_ids.mapped('debit')),
            sum(move.line_ids.mapped('credit')), places=2)

    # ---- ⑤ 人均线三档比例（含空档回退协议）+ 线路维度优先于全局 ----
    def test_per_capita_line_tiers(self):
        pcl = self.env['ta.per.capita.line'].create({
            'base_line': 1000.0, 'excellent_line': 5000.0,
            'base_rate': 10.0, 'standard_rate': 20.0, 'excellent_rate': 35.0})
        pcl.action_active()
        # 基础档：人均 500 < 1000 → 10%
        pa = self._shop_partner('档位A店')
        shop = self._shop(1000.0, 2, partner=pa)
        self._upsert(shop)
        c = self._commission(pa)
        self.assertAlmostEqual(c.per_capita, 500.0)
        self.assertAlmostEqual(c.guide_share_rate, 10.0)
        self.assertAlmostEqual(c.guide_share_before_tax, 30.0)    # 300×10%
        self.assertIn('人均线(全局)', c.rule_note)
        self.assertIn('基础档 10.0%', c.rule_note)
        # 标准档：1000 ≤ 2000 < 5000 → 20%
        pb = self._shop_partner('档位B店')
        shop = self._shop(4000.0, 2, partner=pb)
        self._upsert(shop)
        c = self._commission(pb)
        self.assertAlmostEqual(c.per_capita, 2000.0)
        self.assertAlmostEqual(c.guide_share_rate, 20.0)
        self.assertAlmostEqual(c.guide_share_before_tax, 240.0)   # 1200×20%
        self.assertIn('标准档 20.0%', c.rule_note)
        # 优秀档：6000 ≥ 5000 → 35%，协议奖金 500 叠加（§4.7 奖金口径不变）
        pc = self._shop_partner('档位C店')
        shop = self._shop(12000.0, 2, partner=pc)
        self._upsert(shop)
        c = self._commission(pc)
        self.assertAlmostEqual(c.per_capita, 6000.0)
        self.assertAlmostEqual(c.guide_share_rate, 35.0)
        self.assertAlmostEqual(c.guide_share_before_tax, 1260.0)  # 3600×35%
        self.assertAlmostEqual(c.premium, 500.0)
        self.assertIn('优秀档 35.0%', c.rule_note)
        # 司机/陪同不受人均线影响，仍用协议比例
        d = c.staff_line_ids.filtered(lambda r: r.staff_type == 'driver')
        self.assertAlmostEqual(d.share_rate, 10.0)
        self.assertAlmostEqual(d.share_before_tax, 360.0)

    # ---- ⑥ 空档位回退协议 share_rate ----
    def test_per_capita_line_empty_tier_fallback(self):
        pcl = self.env['ta.per.capita.line'].create({
            'base_line': 1000.0, 'excellent_line': 5000.0,
            'base_rate': 10.0, 'standard_rate': 20.0})   # excellent_rate 留空
        pcl.action_active()
        pa = self._shop_partner('空档店')
        shop = self._shop(12000.0, 2, partner=pa)         # 人均 6000 → 优秀档（空）
        self._upsert(shop)
        c = self._commission(pa)
        self.assertAlmostEqual(c.guide_share_rate, 40.0)  # 回退协议
        self.assertAlmostEqual(c.guide_share_before_tax, 1440.0)
        self.assertIn('回退司陪导协议', c.rule_note)

    # ---- ⑦ 线路维度优先于全局 ----
    def test_per_capita_line_line_priority_over_global(self):
        gbl = self.env['ta.per.capita.line'].create({
            'base_line': 1000.0, 'excellent_line': 5000.0,
            'base_rate': 10.0, 'standard_rate': 20.0, 'excellent_rate': 35.0})
        gbl.action_active()
        ln = self.env['ta.per.capita.line'].create({
            'line_id': self.route.id,
            'base_line': 1000.0, 'excellent_line': 5000.0,
            'base_rate': 15.0, 'standard_rate': 25.0, 'excellent_rate': 45.0})
        ln.action_active()
        pa = self._shop_partner('线路优先店')
        shop = self._shop(4000.0, 2, partner=pa)          # 人均 2000 → 标准档
        self._upsert(shop)
        c = self._commission(pa)
        self.assertAlmostEqual(c.guide_share_rate, 25.0)  # 线路配置，非全局 20%
        self.assertIn(f"线路[{self.route.name}]", c.rule_note)

    # ---- ⑧ 人均线配置缺失 → 与旧口径一致 ----
    def test_no_per_capita_config_legacy(self):
        shop = self._shop(10000.0, 2)
        self._upsert(shop)
        c = self._commission()
        self.assertAlmostEqual(c.per_capita, 5000.0)      # 简单平均 2 位
        self.assertAlmostEqual(c.guide_share_rate, 40.0)  # 协议比例
        self.assertAlmostEqual(c.guide_share_before_tax, 1200.0)
        self.assertAlmostEqual(c.premium, 500.0)
        self.assertAlmostEqual(c.allowance, 2150.0)
        self.assertAlmostEqual(c.company_retain, 850.0)

    # ---- ⑨ 加权平均：按价别加权人数（成人1.0/儿童0.5） ----
    def test_weighted_calc(self):
        calc = self.env['ta.per.capita.calc'].create({
            'calc_mode': 'weighted', 'round_way': 'half_up', 'decimal_places': 2})
        calc.action_active()
        # 追加订单：1 成人 + 2 儿童 → 简单人数 5，加权人数 2+1+0.5+0.5=4.0
        order2 = self.env['ta.order'].create({
            'partner_id': self.customer.id, 'departure_id': self.dep.id,
            'line_ids': [(0, 0, {'name': '丙', 'kind': 'adult'}),
                         (0, 0, {'name': '丁', 'kind': 'child'}),
                         (0, 0, {'name': '戊', 'kind': 'child'})]})
        order2.action_confirm()
        shop = self._shop(10000.0, 2)
        self._upsert(shop)
        c = self._commission()
        self.assertEqual(c.guest_count, 5)
        self.assertAlmostEqual(c.per_capita, 2500.0)      # 10000 ÷ 4.0
        self.assertIn('人均算法', c.rule_note)
        self.assertIn('加权平均', c.rule_note)

    # ---- ⑩ 取整方式生效（向上/向下） ----
    def test_round_way(self):
        calc = self.env['ta.per.capita.calc'].create({
            'calc_mode': 'simple', 'round_way': 'down', 'decimal_places': 2})
        calc.action_active()
        self.order.action_cancel()                        # 释放 2 人
        order3 = self.env['ta.order'].create({
            'partner_id': self.customer.id, 'departure_id': self.dep.id,
            'line_ids': [(0, 0, {'name': 'A', 'kind': 'adult'}),
                         (0, 0, {'name': 'B', 'kind': 'adult'}),
                         (0, 0, {'name': 'C', 'kind': 'adult'})]})
        order3.action_confirm()                           # heads=3
        shop = self._shop(5000.0, 3)
        self._upsert(shop)
        c = self._commission()
        self.assertAlmostEqual(c.per_capita, 1666.66)     # 向下取整
        calc.round_way = 'up'
        self._upsert(shop)
        self.assertAlmostEqual(c.per_capita, 1666.67)     # 向上取整

    # ---- ⑪ 价别加权映射（老人类型缺失 → 1.0 兜底） ----
    def test_kind_weight_map(self):
        self.assertAlmostEqual(_kind_weight('adult'), 1.0)
        self.assertAlmostEqual(_kind_weight('child'), 0.5)
        self.assertAlmostEqual(_kind_weight('child_bed'), 0.5)
        self.assertAlmostEqual(_kind_weight('single'), 1.0)
        self.assertAlmostEqual(_kind_weight('same_tour'), 1.0)
        self.assertAlmostEqual(_kind_weight('elder'), 1.0)   # 老人档未建，兜底 1.0
        self.assertAlmostEqual(_kind_weight('unknown'), 1.0)

    # ---- ⑫ 手工路径不受人均线/算法配置影响（回归） ----
    def test_manual_path_regression(self):
        self.env['ta.per.capita.line'].create({
            'base_line': 1000.0, 'excellent_line': 5000.0,
            'base_rate': 10.0, 'standard_rate': 20.0, 'excellent_rate': 35.0}).action_active()
        self.env['ta.per.capita.calc'].create({
            'calc_mode': 'weighted', 'round_way': 'half_up', 'decimal_places': 2}).action_active()
        c = self.env['ta.guide.commission'].create({
            'guide_id': self.guide.id, 'departure_id': self.dep.id,
            'allowance': 3000.0, 'tax_rate': 0.10})
        self.assertFalse(c.staff_line_ids)
        self.assertAlmostEqual(c.tax_amount, 300.0)
        self.assertAlmostEqual(c.net_amount, 2700.0)
        c.with_user(self.u_acct).action_confirm()
        move = c.move_id.with_user(self.u_acct)
        self.assertEqual(len(move.line_ids), 3)           # 6407/2241/222102
        self.assertAlmostEqual(
            sum(move.line_ids.mapped('debit')),
            sum(move.line_ids.mapped('credit')), places=2)
