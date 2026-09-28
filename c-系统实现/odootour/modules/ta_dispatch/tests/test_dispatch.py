# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger
from odoo.exceptions import UserError


def _get_or_create_account(env, code, name, account_type, **extra):
    """幂等取数（范式同 scripts/seed_ta_demo.py）：正式库存量科目，search by code
    命中即用（name 不同也无妨）；仅在不存在时创建。"""
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
class TestDispatch(TransactionCase):
    """计调确认→供应商账单草稿（幂等）；单团核算 BS-19 口径。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.expense_account = _get_or_create_account(
            cls.env, '6401', '主营业务成本-dispatch测试', 'expense_direct_cost')
        cls.env.company.expense_account_id = cls.expense_account.id
        cls.payable_account = _get_or_create_account(
            cls.env, '2202', '应付账款-dispatch测试', 'liability_payable')
        cls.supplier = cls.env['res.partner'].create({
            'name': '测试车队',
            'property_account_payable_id': cls.payable_account.id})
        cls.purchase_journal = _get_or_create_journal(
            cls.env, 'purchase', '采购测试-dispatch', 'PUCHT')
        route = cls.env['ta.route'].create({
            'name': '计调测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})]})
        route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.order = cls.env['ta.order'].create({
            'departure_id': cls.dep.id,
            'line_ids': [(0, 0, {'name': '李四', 'kind': 'adult'})]})
        cls.order.action_confirm()
        cls.order._ta_apply_paid(3000)  # 模拟已审核收款到账口径

    def _item(self, price=530.0, qty=2.0):
        return self.env['ta.dispatch.item'].create({
            'departure_id': self.dep.id, 'kind': 'vehicle',
            'supplier_id': self.supplier.id, 'name': '旅游大巴',
            'qty': qty, 'unit_price': price})

    def test_confirm_creates_draft_bill(self):
        item = self._item()
        self.assertAlmostEqual(item.amount, 1060.0)
        item.action_confirm()
        self.assertEqual(item.state, 'confirmed')
        self.assertTrue(item.move_id)
        self.assertEqual(item.move_id.state, 'draft')
        self.assertEqual(item.move_id.move_type, 'in_invoice')
        self.assertAlmostEqual(item.move_id.amount_total, 1060.0)
        self.assertAlmostEqual(self.dep.dispatch_cost_total, 1060.0)
        with self.assertRaises(UserError):
            item.action_confirm()  # 幂等：不能重复确认生成第二张

    def test_cancel_unlinks_draft_bill(self):
        item = self._item()
        item.action_confirm()
        move = item.move_id
        item.action_cancel()
        self.assertEqual(item.state, 'cancel')
        self.assertFalse(move.exists())
        item.action_reset_draft()
        self.assertEqual(item.state, 'draft')

    def test_pnl_bs19(self):
        item = self._item(price=530.0, qty=2.0)  # cost_total = 1060
        item.action_confirm()
        self.env.flush_all()  # SQL 视图需先落盘同事务写入
        pnl = self.env['ta.team.pnl'].search([('departure_id', '=', self.dep.id)])
        self.assertEqual(len(pnl), 1)
        self.assertAlmostEqual(pnl.income, 3000.0)
        self.assertAlmostEqual(pnl.cost_total, 1060.0)
        # 不含税拆分关：净额=含税，毛利=收入-成本
        self.assertAlmostEqual(pnl.cost_net, 1060.0)
        self.assertAlmostEqual(pnl.profit, 1940.0)
        # 开：r=6%，cost_net=1060/1.06=1000，profit=2000（BS-19），含税口径仍 1940
        icp = self.env['ir.config_parameter'].sudo()
        icp.set_bool('ta_base.cost_tax_split', True)
        icp.set_float('ta_base.default_tax_rate', 0.06)
        pnl.invalidate_recordset()
        self.assertAlmostEqual(pnl.cost_net, 1000.0, places=2)
        self.assertAlmostEqual(pnl.profit, 2000.0, places=2)
        self.assertAlmostEqual(pnl.profit_tax_incl, 1940.0, places=2)

    def test_negative_price_blocked(self):
        from psycopg2 import IntegrityError
        # 预期内的约束违例仍会触发 odoo.sql_db 的 bad query ERROR 日志，静音之
        with mute_logger('odoo.sql_db'), \
                self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._item(price=-1.0)
