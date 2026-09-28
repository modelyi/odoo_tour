# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestGuidePerformance(TransactionCase):
    """迭代4 T4.1：导游绩效视图数值手算核对（导游×带团月）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.bank_account = cls.env['account.account'].create({
            'name': '银行存款P', 'code': '1004', 'account_type': 'asset_current'})
        cls.loan_account = cls.env['account.account'].create({
            'name': '其他应收款P', 'code': '1222', 'account_type': 'asset_receivable'})
        cls.env['ir.config_parameter'].sudo().set_int(
            'ta_guide.loan_account_id', cls.loan_account.id)
        cls.journal = cls.env['account.journal'].create({
            'name': '绩效发放', 'code': 'BKPG', 'type': 'bank',
            'company_id': cls.company.id,
            'default_account_id': cls.bank_account.id})
        route = cls.env['ta.route'].create({
            'name': '绩效线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]

        def mkdep(date_start, date_end):
            dep = cls.env['ta.departure'].create({
                'route_id': route.id, 'date_start': date_start,
                'date_end': date_end, 'seats_total': 10, 'seats_min': 1})
            dep.action_open()
            dep.action_confirm()
            return dep
        cls.dep6 = mkdep('2026-06-05', '2026-06-07')  # 目标月 2026-06
        cls.dep7 = mkdep('2026-07-05', '2026-07-06')  # 噪声月

        cls.guide = cls.env['res.partner'].create({'name': '李绩效'})
        cls.u_guide = cls.env['res.users'].create({
            'name': '李绩效', 'login': 'perf_t@test.local',
            'company_id': cls.company.id, 'partner_id': cls.guide.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_guide').id])]})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计P', 'login': 'acct_p@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id,
                                  cls.env.ref('ta_base.group_ta_dispatcher').id])]})
        cls.dep6.guide_ids = [(6, 0, [cls.u_guide.id])]
        cls.dep7.guide_ids = [(6, 0, [cls.u_guide.id])]

        partner = cls.env['res.partner'].create({'name': '绩效客户'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': partner.id, 'departure_id': cls.dep6.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()
        # 全额认领到账 → amount_paid=6000（同 BS-19 收入口径）
        cls.order._ta_apply_paid(6000.0)

        supplier = cls.env['res.partner'].create(
            {'name': '绩效票务', 'supplier_rank': 1})
        item = cls.env['ta.dispatch.item'].with_user(cls.u_acct).create({
            'departure_id': cls.dep6.id, 'kind': 'ticket',
            'supplier_id': supplier.id, 'name': '门票', 'qty': 1,
            'unit_price': 1000.0})
        item.with_user(cls.u_acct).action_confirm()

        exp = cls.env['ta.guide.expense'].with_user(cls.u_guide).create({
            'departure_id': cls.dep6.id, 'date': '2026-06-10',
            'line_ids': [(0, 0, {'name': '垫付', 'amount': 460.0})]})
        exp.with_user(cls.u_guide).action_submit()
        exp.with_user(cls.u_acct).action_approve()

        c = cls.env['ta.guide.commission'].with_user(cls.u_acct).create({
            'guide_id': cls.guide.id, 'departure_id': cls.dep6.id,
            'date': '2026-06-10', 'allowance': 3000.0, 'tax_rate': 0.10})
        c.with_user(cls.u_acct).action_settle()  # 无借款：净额 2700 全结

        loan = cls.env['ta.guide.loan'].with_user(cls.u_acct).create({
            'guide_id': cls.guide.id, 'departure_id': cls.dep7.id,
            'amount': 1000.0, 'journal_id': cls.journal.id})
        loan.with_user(cls.u_acct).action_approve()
        loan.with_user(cls.u_acct).action_pay()

    def _row(self, ym):
        rows = self.env['ta.guide.performance'].search(
            [('guide_id', '=', self.guide.id), ('ym', '=', ym)])
        self.assertEqual(len(rows), 1)
        return rows

    def test_performance_numbers(self):
        # T4.1 手算：收入6000 −（计调1000+报账460）= 毛利4540
        row = self._row('2026-06')
        self.assertEqual(row.tour_count, 1)
        self.assertEqual(row.heads, 2)
        self.assertAlmostEqual(row.income, 6000.0)
        self.assertAlmostEqual(row.cost_total, 1460.0)
        self.assertAlmostEqual(row.profit, 4540.0)
        self.assertEqual(row.expense_count, 1)
        self.assertAlmostEqual(row.expense_lag_days, 3.0)  # 06-10 报 − 06-07 结束
        self.assertAlmostEqual(row.commission_net, 2700.0)
        self.assertAlmostEqual(row.loan_outstanding, 1000.0)

    def test_noise_month_separate_row(self):
        row7 = self._row('2026-07')
        self.assertEqual(row7.tour_count, 1)
        self.assertAlmostEqual(row7.income, 0.0)
        self.assertAlmostEqual(row7.commission_net, 0.0)
        self.assertAlmostEqual(row7.loan_outstanding, 1000.0)
