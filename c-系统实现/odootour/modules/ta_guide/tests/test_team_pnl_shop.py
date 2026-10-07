# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


def _get_or_create_account(env, code, name, account_type, **extra):
    """幂等取数（范式同 scripts/seed_ta_demo.py）：search by code 命中即用。"""
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        vals = {'code': code, 'name': name, 'account_type': account_type}
        vals.update(extra)
        acc = env['account.account'].create(vals)
    return acc


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
class TestTeamPnlShop(TransactionCase):
    """批5-迭代3（P0-3 AC-16）：单团损益双口径——
    线路→发团→订单(amount_paid)→计调条目→购物→佣金(确认) 后校验视图行
    profit / profit_no_shop / shop_* 数值；无购物佣金时两口径相等。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.expense_account = _get_or_create_account(
            cls.env, '6401', '主营业务成本-pnl测试', 'expense_direct_cost')
        cls.env.company.expense_account_id = cls.expense_account.id
        _get_or_create_journal(cls.env, 'purchase', '采购测试-pnl', 'PUCPNL')
        # 佣金确认/冲抵凭证需要杂项日记账（BS-08 §4.10）
        cls.gen_journal = _get_or_create_journal(cls.env, 'general', '杂项日记账PNL', 'GENPNL')

        cls.env.user.group_ids = [(4, cls.env.ref('ta_base.group_ta_manager').id)]
        route = cls.env['ta.route'].create({
            'name': '损益双口径测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-11-01',
            'date_end': '2026-11-03', 'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.dep.action_confirm()

        cls.guide = cls.env['res.partner'].create({'name': '损益导游'})
        cls.u_guide = cls.env['res.users'].create({
            'name': '损益导游', 'login': 'pnl_guide@test.local',
            'company_id': cls.company.id, 'partner_id': cls.guide.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_guide').id])]})
        cls.u_acct = cls.env['res.users'].create({
            'name': '会计PNL', 'login': 'pnl_acct@test.local',
            'company_id': cls.company.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('ta_base.group_ta_accountant').id])]})
        cls.dep.guide_ids = [(6, 0, [cls.u_guide.id])]

        cls.customer = cls.env['res.partner'].create({'name': '损益客户'})
        cls.order = cls.env['ta.order'].create({
            'partner_id': cls.customer.id, 'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()  # heads=2
        cls.order._ta_apply_paid(6000.0)  # 模拟已审核收款到账口径

        cls.supplier = cls.env['res.partner'].create({'name': '损益车队'})
        cls.item = cls.env['ta.dispatch.item'].create({
            'departure_id': cls.dep.id, 'kind': 'vehicle',
            'supplier_id': cls.supplier.id, 'name': '旅游大巴',
            'qty': 2, 'unit_price': 530})
        cls.item.action_confirm()  # 已确认计调条目 → cost_total = 1060

        cls.shop_partner = cls.env['res.partner'].create(
            {'name': '翡翠购物店PNL', 'supplier_rank': 1})
        cls.agreement = cls.env['ta.shop.agreement'].create({
            'shop_partner_id': cls.shop_partner.id,
            'begin_date': '2026-01-01', 'end_date': '2026-12-31',
            'base_rate': 20.0})
        cls.agreement.action_active()
        cls.staff_agr = cls.env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': cls.guide.id,
            'tax_type': 'labor', 'id_number': '****5678',
            'share_rate': 40.0})
        cls.staff_agr.action_active()

    def _pnl(self):
        self.env.flush_all()  # SQL 视图同事务写入需先落盘
        return self.env['ta.team.pnl'].search([('departure_id', '=', self.dep.id)])

    def _shopping_flow(self):
        shop = self.env['ta.shop'].create({
            'departure_id': self.dep.id,
            'shop_partner_id': self.shop_partner.id,
            'shop_date': '2026-11-02',
            'guest_count': 2,
            'total_amount': 10000.0,
            'guide_id': self.guide.id,
        })
        shop.with_user(self.u_acct).action_confirm()
        commission = self.env['ta.guide.commission'].search([
            ('departure_id', '=', self.dep.id),
            ('shop_partner_id', '=', self.shop_partner.id),
        ], limit=1)
        commission.with_user(self.u_acct).action_confirm()
        return commission

    def test_pnl_dual_profit_with_shop(self):
        """含购物：profit = profit_no_shop + (佣金总额 − 销项税) − 司陪分成。"""
        commission = self._shopping_flow()
        pnl = self._pnl()
        self.assertTrue(pnl, '视图应包含该发团计划行')
        # 基础口径：收入 6000，成本 1060（默认不拆税 → cost_net = cost_total）
        self.assertAlmostEqual(pnl.income, 6000.0)
        self.assertAlmostEqual(pnl.cost_total, 1060.0)
        self.assertAlmostEqual(pnl.cost_net, 1060.0)
        self.assertAlmostEqual(pnl.profit_no_shop, 4940.0)
        # 购物佣金三列：人均 5000 → 基础比例 20% → 佣金 2000；分成 40% → 800（≤800 不预扣）
        self.assertAlmostEqual(commission.commission_total, 2000.0)
        self.assertAlmostEqual(pnl.shop_commission, 2000.0)
        self.assertAlmostEqual(pnl.shop_commission_tax, 0.0)  # 税率未配置
        self.assertAlmostEqual(pnl.shop_staff_cost, 800.0)
        # AC-16 含购物口径：4940 + (2000 − 0) − 800 = 6140
        self.assertAlmostEqual(pnl.profit, 6140.0)
        self.assertAlmostEqual(pnl.profit_tax_incl, 4940.0)

    def test_pnl_no_shop_equals(self):
        """无购物佣金时含购物口径 == 不含购物口径（profit == profit_no_shop）。"""
        pnl = self._pnl()
        self.assertTrue(pnl)
        self.assertAlmostEqual(pnl.shop_commission, 0.0)
        self.assertAlmostEqual(pnl.profit, pnl.profit_no_shop)
