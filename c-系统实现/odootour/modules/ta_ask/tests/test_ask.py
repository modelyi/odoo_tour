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
            'line_ids': [(0, 0, {'name': '甲', 'kind': 'adult'}),
                         (0, 0, {'name': '乙', 'kind': 'adult'})]})
        cls.order.action_confirm()
        cls.order._ta_apply_paid(2000)
        bank_acct = cls.env['account.account'].create({
            'code': '5029TBA', 'name': '问数测试银行', 'account_type': 'asset_cash'})
        bank_journal = cls.env['account.journal'].create({
            'name': '问数测试银行账户', 'type': 'bank', 'code': 'TBAK',
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
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {
            'choices': [{'message': {'content': json.dumps(payload, ensure_ascii=False)}}]}
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
        self.assertNotIn('4000', reply.body or '')

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
        self.assertEqual(data['rows'][0][1:], [1, 2, 6000])
        data = self.env['ta.order']._ask_receivable_top({})
        self.assertEqual(data['rows'][0][3:], [6000, 2000, 4000])
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
