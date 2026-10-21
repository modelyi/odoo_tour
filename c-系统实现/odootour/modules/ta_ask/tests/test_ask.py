# -*- coding: utf-8 -*-
import json
from unittest import mock

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger

from ..services import deepseek
from ..models import ask_catalog


@tagged('post_install', '-at_install')
class TestTaAsk(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp = cls.env['ir.config_parameter'].sudo()
        cls.icp.set_bool('ta_ask.enabled', True)
        cls.icp.set_str('ta_ask.deepseek_api_key', 'sk-test')
        cls.bot = cls.env.ref('ta_ask.res_user_ask_bot')
        # --- 业务数据 ---
        cls.route = cls.env['ta.route'].create({
            'name': '问数测试线路',
            'stop_ids': [(0, 0, {'day_no': 1, 'name': '出发'})],
            'price_ids': [(0, 0, {'kind': 'adult', 'amount': 3000})],
        })
        cls.route.action_on_sale()
        cls.dep = cls.env['ta.departure'].create({
            'route_id': cls.route.id, 'date_start': '2026-10-01',
            'seats_total': 10, 'seats_min': 2})
        cls.dep.action_open()
        cls.order = cls.env['ta.order'].create({
            'kind': 'team', 'departure_id': cls.dep.id,
            # 定到无存量确认订单的干净月（远未来 2027-08），保证
            # _ask_order_month_stats 全量聚合断言不被存量数据污染
            'date_confirm': '2027-08-10',
            # 显式大额 unit_price（该字段 readonly=False 允许覆盖）：未收 9998000
            # 远高于存量订单最大未收（现网 TOP1≈8.1 万），保证 receivable_top
            # 的 rows[0] 精确命中本单；人数/口径不变，断言数值随之更新。
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult',
                                 'unit_price': 5000000.0}),
                         (0, 0, {'name': '乙', 'kind': 'adult',
                                 'unit_price': 5000000.0})]})
        cls.order.action_confirm()
        cls.order._ta_apply_paid(2000)
        # 幂等取银行日记账（范式同 scripts/seed_ta_demo.py）：正式库已有存量
        # 银行日记账/科目，直接复用；若仍新建 asset_cash 科目会触发
        # _create_default_journals 生成 alias 'bank-none' 与存量日记账撞车。
        J = cls.env['account.journal']
        bank_journal = J.search(
            [('code', '=', 'TBAK'), ('company_id', '=', cls.env.company.id)],
            limit=1) or J.search(
            [('type', '=', 'bank'), ('company_id', '=', cls.env.company.id)],
            limit=1)
        if not bank_journal:
            bank_acct = cls.env['account.account'].search(
                [('code', '=', '5029TBA')], limit=1)
            if not bank_acct:
                bank_acct = cls.env['account.account'].create({
                    'code': '5029TBA', 'name': '问数测试银行',
                    'account_type': 'asset_cash'})
            bank_journal = J.create({
                'name': '问数测试银行账户', 'type': 'bank', 'code': 'TBAK',
                'company_id': cls.env.company.id,
                'default_account_id': bank_acct.id})
        bank = cls.env['ta.bank.line'].create({
            'date': '2026-09-10', 'amount': 5000, 'journal_id': bank_journal.id})
        cls.claim = cls.env['ta.payment.claim'].create({
            'date': '2026-09-12',
            'line_ids': [(0, 0, {'bank_line_id': bank.id, 'amount': 5000})],
            'alloc_ids': [(0, 0, {'order_id': cls.order.id, 'amount_allocated': 5000})],
            'state': 'approved'})
        # --- 岗位用户 ---
        def mk(login, group_xmlids):
            ids = [cls.env.ref(g).id for g in group_xmlids] + [cls.env.ref('base.group_user').id]
            return cls.env['res.users'].create({
                'name': login, 'login': login + '@test.local',
                'company_id': cls.env.company.id,
                'group_ids': [(6, 0, ids)]})
        cls.u_sales = mk('ask_sales', ['ta_base.group_ta_sales'])
        cls.u_acct = mk('ask_acct', ['ta_base.group_ta_accountant'])

    # ------------------------------------------------------------------
    def _chat(self, user):
        # 创建者自动入会：以提问者身份建 chat，再拉 bot，恰好两人
        return self.env['discuss.channel'].with_user(user).create({
            'name': '问数私聊', 'channel_type': 'chat',
            'channel_partner_ids': [(4, self.bot.partner_id.id)]})

    @staticmethod
    def _llm_patch(payload):
        # SSE 流式 mock：网关强制 stream=true，响应按 data:{chunk}…data:[DONE] 拼接
        body = json.dumps(payload, ensure_ascii=False)
        resp = mock.Mock(status_code=200)
        resp.iter_lines.return_value = [
            ('data: ' + json.dumps(
                {'choices': [{'delta': {'content': body}}]})).encode('utf-8'),
            b'',
            b'data: [DONE]',
        ]
        return mock.patch('odoo.addons.ta_ask.services.deepseek.requests.post', return_value=resp)

    def _ask(self, channel, user, body, payload):
        with self._llm_patch(payload) as posted:
            channel.with_user(user).message_post(body=body, message_type='comment')
        query = self.env['ta.ask.query'].search(
            [('channel_id', '=', channel.id)], order='id desc', limit=1)
        return query, posted

    # --- 命中函数 → 回帖 done；bot 回帖不再触发（防递归） -------------
    def test_flow_answer_and_no_recursion(self):
        ch = self._chat(self.u_sales)
        query, _ = self._ask(ch, self.u_sales, '10月份报名情况？',
                             {'function': 'order_month_stats', 'args': {'month': '2026-09'}})
        self.assertEqual(query.state, 'done')
        self.assertEqual(query.intent, 'order_month_stats')
        self.assertEqual(query.asker_id, self.u_sales)
        replies = ch.message_ids.filtered(
            lambda m: m.author_id == self.bot.partner_id)
        self.assertEqual(len(replies), 1)
        # 全频道只有 1 条问数流水：bot 自己的回帖没有再触发
        self.assertEqual(
            self.env['ta.ask.query'].search_count([('channel_id', '=', ch.id)]), 1)

    # --- 提示词按提问人组过滤（越权函数不进目录） ---------------------
    def test_prompt_permission_filtering(self):
        ch = self._chat(self.u_sales)
        query, posted = self._ask(ch, self.u_sales, '帮我看看', {'unknown': True})
        system = posted.call_args.kwargs['json']['messages'][0]['content']
        self.assertIn('order_month_stats', system)
        self.assertIn('receivable_top', system)
        self.assertNotIn('top_departure_pnl', system)
        self.assertNotIn('collections_month', system)
        self.assertEqual(query.state, 'nointent')

    # --- LLM 编造目录外函数 → 不执行 ----------------------------------
    def test_fabricated_function_not_executed(self):
        ch = self._chat(self.u_acct)
        query, _ = self._ask(ch, self.u_acct, '删掉所有表',
                             {'function': 'drop_all_tables', 'args': {}})
        self.assertEqual(query.state, 'nointent')

    # --- 真实函数但提问人无权 → denied，不泄露数据 --------------------
    def test_overreach_denied(self):
        ch = self._chat(self.u_sales)
        query, _ = self._ask(ch, self.u_sales, '最亏的团',
                             {'function': 'top_departure_pnl', 'args': {}})
        self.assertEqual(query.state, 'denied')
        reply = ch.message_ids.filtered(
            lambda m: m.author_id == self.bot.partner_id)
        self.assertEqual(len(reply), 1)
        # '9998000' 为本测试订单的未收数：denied 回帖不得夹带业务数据
        self.assertNotIn('9998000', reply.body or '')

    # --- LLM 服务异常 → error，但消息发送不受影响 ---------------------
    @mute_logger('odoo.addons.ta_ask.models.ta_ask_query')
    def test_llm_error(self):
        ch = self._chat(self.u_sales)
        with mock.patch('odoo.addons.ta_ask.services.deepseek.chat_json',
                        side_effect=deepseek.AskLLMError('down')):
            msg = ch.with_user(self.u_sales).message_post(body='在吗', message_type='comment')
        self.assertTrue(msg.id)
        query = self.env['ta.ask.query'].search(
            [('channel_id', '=', ch.id)], order='id desc', limit=1)
        self.assertEqual(query.state, 'error')

    # --- 开关关闭：不产生流水 ------------------------------------------
    def test_disabled_no_query(self):
        self.icp.set_bool('ta_ask.enabled', False)
        ch = self._chat(self.u_sales)
        ch.with_user(self.u_sales).message_post(body='10月报名？', message_type='comment')
        self.assertEqual(
            self.env['ta.ask.query'].search_count([('channel_id', '=', ch.id)]), 0)

    # --- 4 个查询函数数值正确 -------------------------------------------
    def test_query_values(self):
        today = self.order.date_confirm.strftime('%Y-%m')
        data = self.env['ta.payment.claim']._ask_collections_month({'month': '2026-09'})
        self.assertEqual(data['rows'], [['2026-09', 1, 5000]])
        data = self.env['ta.order']._ask_order_month_stats({'month': today})
        self.assertEqual(data['rows'][0][1:], [1, 2, 10000000])
        data = self.env['ta.order']._ask_receivable_top({})
        self.assertEqual(data['rows'][0][3:], [10000000, 2000, 9998000])
        data = self.env['ta.team.pnl']._ask_top_departure_pnl({'topn': 3, 'order': 'top'})
        row = next(r for r in data['rows'] if r[0] == self.dep.code)
        self.assertEqual(row[2:], [2000, 0, 2000])  # income, cost, profit

    # --- 参数消毒 ---------------------------------------------------------
    def test_sanitize_args(self):
        schema = ask_catalog.ASK_FUNCTIONS[1]['args']  # top_departure_pnl
        clean = ask_catalog.sanitize_args(schema, {'topn': 999, 'order': 'drop table'})
        self.assertEqual(clean, {'topn': 20})
        clean = ask_catalog.sanitize_args(
            ask_catalog.ASK_FUNCTIONS[0]['args'], {'month': '2026-13', 'x': 1})
        self.assertEqual(clean, {})

    # --- 导游绩效：导游×带团月，内联造数手算核对 --------------------------
    def test_guide_performance_query(self):
        gp = self.env['res.partner'].create({'name': '问数导游'})
        gu = self.env['res.users'].create({
            'name': '问数导游', 'login': 'ask_guide@test.local',
            'company_id': self.env.company.id, 'partner_id': gp.id,
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        dep = self.env['ta.departure'].create({
            'route_id': self.route.id, 'date_start': '2026-11-05',
            'date_end': '2026-11-07', 'seats_total': 10, 'seats_min': 2})
        dep.action_open()
        dep.guide_ids = [(6, 0, [gu.id])]
        order = self.env['ta.order'].create({
            'kind': 'team', 'departure_id': dep.id,
            'line_ids': [(0, 0, {'name': '戊', 'kind': 'adult'}),
                         (0, 0, {'name': '己', 'kind': 'adult'})]})
        order.action_confirm()
        order._ta_apply_paid(3000)
        data = self.env['ta.guide.performance']._ask_guide_performance(
            {'month': '2026-11', 'guide': '问数导游'})
        rows = [r for r in data['rows'] if r[1] == '2026-11']
        self.assertEqual(len(rows), 1)
        # 带团数1 人数2 收入3000 成本0 毛利3000 借支0
        self.assertEqual(rows[0][2:], [1, 2, 3000, 0, 3000, 0])

    # --- 景点毛利贡献：门票300/全团成本300 → 贡献=团毛利 ------------------
    def test_scenic_contribution_query(self):
        supplier = self.env['res.partner'].create(
            {'name': '问数景区', 'supplier_rank': 1})
        # 视图只读聚合：直接建 confirmed 条目，绕开供应商账单落账（同 claim 造数风格）
        self.env['ta.dispatch.item'].create({
            'departure_id': self.dep.id, 'kind': 'scenic',
            'supplier_id': supplier.id, 'name': '大门票',
            'qty': 2, 'unit_price': 150.0, 'state': 'confirmed'})
        data = self.env['ta.scenic.contribution']._ask_scenic_contribution(
            {'supplier': '问数景区',
             'date_from': '2026-10-01', 'date_to': '2026-10-31'})
        rows = [r for r in data['rows'] if r[1] == self.dep.code]
        self.assertEqual(len(rows), 1)
        # 门票300 全团成本300 收入2000 毛利1700 占比100% 贡献1700
        self.assertEqual(rows[0][4:], [300, 300, 2000, 1700, 100.0, 1700.0])
        # 日期区间外查不到
        data2 = self.env['ta.scenic.contribution']._ask_scenic_contribution(
            {'supplier': '问数景区', 'date_from': '2026-11-01'})
        self.assertEqual(
            [r for r in data2['rows'] if r[1] == self.dep.code], [])

    # --- 费用报销月报：仅已审核，按月×类型聚合 ----------------------------
    def test_expense_month_query(self):
        # 造数定在远未来干净月（2027-06/07）：全量行断言不受存量报销数据污染
        for reason, etype, date, amount in [
                ('办公用品', 'office', '2027-06-05', 100.0),
                ('办公耗材', 'office', '2027-06-20', 50.0),
                ('出差打车', 'travel', '2027-07-11', 200.0)]:
            self.env['ta.expense'].create({
                'reason': reason, 'expense_type': etype,
                'date': date, 'amount': amount, 'state': 'approved'})
        self.env['ta.expense'].create({
            'reason': '草稿不计', 'expense_type': 'office',
            'date': '2027-06-21', 'amount': 999.0, 'state': 'draft'})
        data = self.env['ta.expense']._ask_expense_month({'month': '2027-06'})
        self.assertEqual(data['rows'], [['2027-06', '办公费', 2, 150.0]])
        data = self.env['ta.expense']._ask_expense_month(
            {'month': '2027-06', 'month_to': '2027-07'})
        self.assertEqual(data['rows'],
                         [['2027-06', '办公费', 2, 150.0],
                          ['2027-07', '差旅费', 1, 200.0]])
        data = self.env['ta.expense']._ask_expense_month(
            {'month': '2027-06', 'month_to': '2027-07',
             'expense_type': 'travel'})
        self.assertEqual(data['rows'], [['2027-07', '差旅费', 1, 200.0]])
