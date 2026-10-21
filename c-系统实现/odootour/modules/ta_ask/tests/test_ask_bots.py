# -*- coding: utf-8 -*-
"""问数 2.0（领域机器人）测试：

- 目录按机器人领域 ∩ 提问人组过滤；
- 私聊财务问数 bot：persona 注入、done、以财务 bot 身份回帖；
- 销售 + 导游 bot：目录空交集 → denied（权限口径仍是提问人）；
- 新增查询函数：账龄 TOP / 供应商未付 / 收入确认月报 / 计调成本分类 /
  导游借支 / 佣金月报 / 报账月报。
"""
from odoo.tests.common import tagged

from ..models import ask_catalog
from .test_ask import TestTaAsk


@tagged('post_install', '-at_install')
class TestAskBots(TestTaAsk):

    def _chat_with(self, user, bot_user):
        return self.env['discuss.channel'].with_user(user).create({
            'name': '领域问数私聊', 'channel_type': 'chat',
            'channel_partner_ids': [(4, bot_user.partner_id.id)]})

    # --- 目录过滤：机器人领域 ∩ 提问人组 -------------------------------
    def test_catalog_bot_filtering(self):
        def names(user, bot=None):
            return [f['name'] for f in ask_catalog.catalog_for_user(user, bot)]
        all_acct = names(self.u_acct)
        self.assertIn('aging_top', all_acct)
        self.assertIn('guide_commission_month', all_acct)
        fin = names(self.u_acct, 'finance')
        self.assertIn('aging_top', fin)
        self.assertIn('dispatch_cost_by_kind', fin)
        self.assertIn('supplier_payable_top', fin)
        self.assertNotIn('guide_commission_month', fin)
        gui = names(self.u_acct, 'guide')
        self.assertIn('guide_commission_month', gui)
        self.assertIn('guide_loan_outstanding', gui)
        self.assertNotIn('aging_top', gui)
        # 销售提问财务 bot：只见"销售组 ∩ 财务域"的函数
        fin_sales = names(self.u_sales, 'finance')
        self.assertIn('receivable_top', fin_sales)
        self.assertIn('aging_top', fin_sales)
        self.assertNotIn('guide_performance', fin_sales)
        self.assertNotIn('collections_month', fin_sales)

    # --- 私聊财务 bot：persona + done + 财务 bot 身份回帖 ---------------
    def test_finance_bot_chat_flow(self):
        fbot = self.env.ref('ta_ask.res_user_finance_bot')
        ch = self._chat_with(self.u_acct, fbot)
        query, posted = self._ask(
            ch, self.u_acct, '账龄最差的订单',
            {'function': 'aging_top', 'args': {}})
        self.assertEqual(query.state, 'done')
        self.assertEqual(query.bot_code, 'finance')
        self.assertEqual(query.bot_user_id, fbot)
        system = posted.call_args.kwargs['json']['messages'][0]['content']
        self.assertIn('财务问数机器人', system)      # persona 注入
        self.assertNotIn('guide_commission_month', system)  # 导游域函数不进目录
        replies = ch.message_ids.filtered(
            lambda m: m.author_id == fbot.partner_id)
        self.assertEqual(len(replies), 1)
        # 本测试订单未收 9,998,000 为全库最大 → 账龄 TOP1
        self.assertIn('9,998,000', replies.body or '')

    # --- 销售 + 导游 bot：目录空交集 → denied ---------------------------
    def test_guide_bot_denied_for_sales(self):
        gbot = self.env.ref('ta_ask.res_user_guide_bot')
        ch = self._chat_with(self.u_sales, gbot)
        query, _ = self._ask(
            ch, self.u_sales, '导游绩效',
            {'function': 'guide_performance', 'args': {}})
        self.assertEqual(query.state, 'denied')
        self.assertEqual(query.bot_code, 'guide')

    # --- 导游域查询函数 --------------------------------------------------
    def test_guide_domain_queries(self):
        guide = self.env['res.partner'].create({'name': '张三丰'})
        loan = self.env['ta.guide.loan'].create({
            'guide_id': guide.id, 'departure_id': self.dep.id,
            'amount': 5000.0, 'date': '2026-11-01', 'due_date': '2026-11-20'})
        data = self.env['ta.guide.loan']._ask_guide_loan_outstanding(
            {'guide': '张三丰'})
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0][1], '张三丰')
        self.assertAlmostEqual(data['rows'][0][5], 5000.0)  # 未结清

        self.env['ta.guide.expense'].create({
            'guide_id': guide.id, 'departure_id': self.dep.id,
            'date': '2026-11-08',
            'line_ids': [(0, 0, {'name': '餐费', 'amount': 600.0})],
            'state': 'approved'})
        data = self.env['ta.guide.expense']._ask_guide_expense_month(
            {'month': '2026-11'})
        self.assertEqual(data['rows'][0][0], '张三丰')
        self.assertEqual(data['rows'][0][1], 1)
        self.assertAlmostEqual(data['rows'][0][2], 600.0)

        self.env['ta.guide.commission'].create({
            'guide_id': guide.id, 'departure_id': self.dep.id,
            'date': '2026-11-05', 'allowance': 100.0, 'state': 'confirmed'})
        data = self.env['ta.guide.commission']._ask_guide_commission_month(
            {'month': '2026-11'})
        self.assertEqual(len(data['rows']), 1)
        self.assertEqual(data['rows'][0][1], 1)  # 佣金单数

    # --- 财务域查询函数 --------------------------------------------------
    def test_finance_domain_queries(self):
        sup = self.env['res.partner'].create({'name': '问数测试车队B'})
        self.env['ta.dispatch.item'].create({
            'departure_id': self.dep.id, 'kind': 'vehicle',
            'supplier_id': sup.id, 'name': '大巴',
            'qty': 1.0, 'unit_price': 300.0, 'state': 'confirmed'})
        self.env.flush_all()
        data = self.env['ta.supplier.payable']._ask_supplier_payable_top(
            {'topn': 20})
        row = [r for r in data['rows'] if r[0] == '问数测试车队B']
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row[0][7], 300.0)  # 未付余额

        data = self.env['ta.dispatch.item']._ask_dispatch_cost_by_kind(
            {'month': '2026-10'})
        row = [r for r in data['rows'] if r[0] == '车队']
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row[0][2], 300.0)  # dep 出发 2026-10-01

        self.env['ta.revenue.recognition'].create({
            'departure_id': self.dep.id, 'date': '2026-11-05',
            'biz_mode_code': '1', 'mode': 'gross',
            'gross_amount': 1000.0, 'net_amount': 943.39,
            'tax_amount': 56.61, 'state': 'posted'})
        data = self.env['ta.revenue.recognition']._ask_revenue_month(
            {'month': '2026-11'})
        self.assertEqual(data['rows'][0][0], '2026-11')
        self.assertEqual(data['rows'][0][1], 1)
        self.assertAlmostEqual(data['rows'][0][2], 1000.0)
        self.assertAlmostEqual(data['rows'][0][3], 943.39)
        self.assertAlmostEqual(data['rows'][0][4], 56.61)


@tagged('post_install', '-at_install')
class TestLLMGatewayCompat(TestTaAsk):
    """网关兼容：不支持 response_format 的 OpenAI 兼容网关（如 CodeBuddy）
    首次 400 → 自动去掉该参数重试一次 → 正常解析。"""

    def test_response_format_downgrade(self):
        from unittest import mock
        import json as _json
        from ..services import deepseek as ds

        ok_resp = mock.Mock(status_code=200)
        ok_resp.json.return_value = {'choices': [{
            'message': {'content': _json.dumps(
                {'function': 'order_month_stats', 'args': {}})}}]}
        bad_resp = mock.Mock(status_code=400)
        with mock.patch('odoo.addons.ta_ask.services.deepseek.requests.post',
                        side_effect=[bad_resp, ok_resp]) as posted:
            data = ds.chat_json(
                api_key='ck-test', base_url='https://www.codebuddy.cn/v2',
                model='codebuddy', messages=[{'role': 'user', 'content': 'q'}])
        self.assertEqual(data['function'], 'order_month_stats')
        self.assertEqual(posted.call_count, 2)
        # 第一次带 response_format，第二次（降级重试）不带
        self.assertIn('response_format',
                      posted.call_args_list[0].kwargs['json'])
        self.assertNotIn('response_format',
                         posted.call_args_list[1].kwargs['json'])
        # CodeBuddy 网关 URL 拼接正确
        self.assertEqual(posted.call_args_list[0].args[0],
                         'https://www.codebuddy.cn/v2/chat/completions')
