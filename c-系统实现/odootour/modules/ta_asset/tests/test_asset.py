# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, AccessError


@tagged('post_install', '-at_install')
class TestAsset(TransactionCase):
    """资产卡片 + 直线法月折旧 + 计提幂等 + 处置停提。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.dep_account = cls.env['account.account'].create({
            'name': '折旧费测试', 'code': '660201', 'account_type': 'expense'})
        cls.accum_account = cls.env['account.account'].create({
            'name': '累计折旧测试', 'code': '160201', 'account_type': 'liability_current'})
        cls.journal = cls.env['account.journal'].create({
            'name': '资产折旧测试', 'code': 'ASSTST', 'type': 'general',
            'company_id': cls.company.id})
        icp = cls.env['ir.config_parameter'].sudo()
        for key, val in (('ta_asset.depreciation_account_id', cls.dep_account.id),
                         ('ta_asset.accumulated_account_id', cls.accum_account.id)):
            rec = icp.search([('key', '=', key)], limit=1)
            if rec:
                rec.value = str(val)
            else:
                icp.create({'key': key, 'value': str(val)})

        def mk(login, group_xmlids):
            groups = [cls.env.ref(g).id for g in group_xmlids] + [cls.env.ref('base.group_user').id]
            return cls.env['res.users'].create({
                'name': login, 'login': login + '@test.local',
                'company_id': cls.company.id,
                'group_ids': [(6, 0, groups)]})
        cls.u_sales = mk('asset_sales_t', ['ta_base.group_ta_sales'])
        cls.u_acct = mk('asset_acct_t', ['ta_base.group_ta_accountant'])

    def _asset(self, **kw):
        vals = dict(name='测试大巴', category='vehicle', cost=100000.0,
                    residual_rate=5.0, depreciation_months=48,
                    acquisition_date='2026-01-15')
        vals.update(kw)
        return self.env['ta.asset'].create(vals)

    def test_monthly_depreciation_math(self):
        # T2.1 直线法：100000×(1−5%)÷48 = 1979.17
        asset = self._asset()
        self.assertAlmostEqual(asset.monthly_depreciation, 1979.17)
        self.assertAlmostEqual(asset.book_value, 100000.0)

    def test_depreciate_wizard_posts_move(self):
        # T2.2 计提至 2026-03 → 1/2/3 月各一条，凭证已过账、科目正确
        asset = self._asset()
        asset.with_user(self.u_acct).action_validate()
        wiz = self.env['ta.asset.depreciate.wizard'].with_user(self.u_acct).create({
            'period_to': '2026-03', 'post_moves': True})
        wiz.action_run()
        deps = asset.depreciation_line_ids.sorted('period')
        self.assertEqual(deps.mapped('period'), ['2026-01', '2026-02', '2026-03'])
        self.assertAlmostEqual(sum(deps.mapped('amount')), 1979.17 * 3)
        moves = deps.move_id
        self.assertEqual(len(moves), 3)
        self.assertEqual(set(moves.mapped('state')), {'posted'})
        first = moves[0].sudo().line_ids
        self.assertEqual(first.filtered(lambda l: l.debit).account_id, self.dep_account)
        self.assertEqual(first.filtered(lambda l: l.credit).account_id, self.accum_account)
        self.assertAlmostEqual(asset.book_value, 100000.0 - 1979.17 * 3)

    def test_depreciate_idempotent(self):
        # T2.3 重跑不重复计提（unique 约束 + 已存在期间跳过）
        asset = self._asset()
        asset.with_user(self.u_acct).action_validate()
        wiz = self.env['ta.asset.depreciate.wizard'].with_user(self.u_acct).create({
            'period_to': '2026-02', 'post_moves': False})
        wiz.action_run()
        wiz.action_run()
        self.assertEqual(len(asset.depreciation_line_ids), 2)

    def test_dispose_stops_depreciation(self):
        # T2.4 已处置资产不再被批量计提
        asset = self._asset()
        asset.with_user(self.u_acct).action_validate()
        asset.with_user(self.u_acct).action_dispose()
        self.assertEqual(asset.state, 'disposed')
        self.env['ta.asset.depreciate.wizard'].with_user(self.u_acct).create({
            'period_to': '2026-03', 'post_moves': False}).action_run()
        self.assertFalse(asset.depreciation_line_ids)

    def test_validate_requires_accountant(self):
        asset = self._asset()
        with self.assertRaises(AccessError):
            asset.with_user(self.u_sales).action_validate()

    def test_period_unique_constraint(self):
        from psycopg2.errors import UniqueViolation
        asset = self._asset()
        self.env['ta.asset.depreciation'].create({
            'asset_id': asset.id, 'period': '2026-01', 'amount': 100.0})
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self.env['ta.asset.depreciation'].create({
                'asset_id': asset.id, 'period': '2026-01', 'amount': 50.0})
