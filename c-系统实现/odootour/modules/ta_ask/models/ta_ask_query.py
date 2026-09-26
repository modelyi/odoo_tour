# -*- coding: utf-8 -*-
import json
import logging
import re
import time

from markupsafe import Markup

from odoo import api, models, fields
from odoo.exceptions import AccessError, UserError

from ..services import deepseek
from . import ask_catalog, ask_format

_logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TMPL = (
    "你是旅行社管理系统的问数助手。你只能从下面的【可用查询目录】中选择一个函数，"
    "并把用户问题映射为严格的 JSON 输出，禁止编造目录外的函数，禁止输出任何 SQL。\n"
    "输出格式（二选一）：\n"
    '{{"function": "<目录中的name>", "args": {{...}}}}\n'
    '或 {{"clarify": "<需要用户补充的信息，一句话>"}}\n'
    "如果问题与目录中任何函数都不相关，输出 {{\"unknown\": true}}。\n"
    "今天日期：{today}。当前统计周期缺省时按最近理解。\n\n"
    "【可用查询目录】\n{catalog}\n\n"
    "示例：\n{examples}"
)


def html_to_text(body):
    if not body:
        return ''
    text = re.sub(r'<[^>]+>', ' ', str(body))
    import html as html_mod
    text = html_mod.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


class TaAskQuery(models.Model):
    _name = 'ta.ask.query'
    _inherit = ['ta.mixin']
    _description = 'Discuss 问数流水'
    _order = 'id desc'

    asker_id = fields.Many2one('res.users', string='提问人', required=True, index=True)
    channel_id = fields.Many2one('discuss.channel', string='频道')
    message_id = fields.Many2one('mail.message', string='提问消息')
    question = fields.Text(string='问题')
    intent = fields.Char(string='命中函数')
    result_brief = fields.Text(string='结果摘要')
    state = fields.Selection([
        ('pending', '待处理'),
        ('done', '已回答'),
        ('clarify', '待澄清'),
        ('denied', '无权限'),
        ('nointent', '超出范围'),
        ('error', '服务异常'),
    ], string='状态', default='pending', required=True, index=True)
    latency_ms = fields.Integer(string='耗时(ms)')
    reply_message_id = fields.Many2one('mail.message', string='回复消息')

    # ------------------------------------------------------------------
    # 分发器
    # ------------------------------------------------------------------
    @api.model
    def _ask_build_messages(self, asker, question):
        catalog = ask_catalog.catalog_for_user(asker)
        slim = [{'name': f['name'], 'description': f['description'],
                 'args': {k: v['desc'] for k, v in f['args'].items()}}
                for f in catalog]
        ex_lines = []
        for f in catalog[:3]:
            q, ex_args = f.get('example') or ('', None)
            if q:
                ex_lines.append('问：%s 答：%s' % (
                    q, json.dumps({'function': f['name'], 'args': ex_args},
                                  ensure_ascii=False)))
        system = SYSTEM_PROMPT_TMPL.format(
            today=fields.Date.context_today(self),
            catalog=json.dumps(slim, ensure_ascii=False),
            examples='\n'.join(ex_lines) or '（无）')
        return [{'role': 'system', 'content': system},
                {'role': 'user', 'content': question}]

    def _ask_reply(self, body_markup, channel, parent_message):
        """以 bot 身份回帖；bot 必须已在频道内。"""
        self.ensure_one()
        bot = self.env.ref('ta_ask.res_user_ask_bot')
        if not channel:
            return None
        return channel.sudo().message_post(
            author_id=bot.partner_id.id,
            body=body_markup,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    def _ask_process(self):
        """处理一条问数流水（同步入口与 cron 共用）。幂等：仅 pending 会被消费。"""
        self.ensure_one()
        if self.state != 'pending':
            return
        icp = self.env['ir.config_parameter'].sudo()
        asker = self.asker_id
        start = time.time()
        try:
            messages = self._ask_build_messages(asker, self.question or '')
            payload = deepseek.chat_json(
                api_key=icp.get_str('ta_ask.deepseek_api_key', ''),
                base_url=icp.get_str('ta_ask.deepseek_base_url', 'https://api.deepseek.com/v1'),
                model=icp.get_str('ta_ask.deepseek_model', 'deepseek-chat'),
                messages=messages,
                timeout=icp.get_float('ta_ask.timeout', 12.0) or 12.0,
            )
        except deepseek.AskLLMError as e:
            self.write({'state': 'error', 'intent': 'llm_error',
                        'result_brief': str(e)[:200],
                        'latency_ms': int((time.time() - start) * 1000)})
            self._ask_reply(ask_format.reply_error(), self.channel_id, self.message_id)
            return
        self._ask_execute_intent(payload, asker, start)

    def _ask_execute_intent(self, payload, asker, start):
        catalog = ask_catalog.catalog_for_user(asker)
        by_name = {f['name']: f for f in catalog}
        if payload.get('clarify'):
            self.write({'state': 'clarify', 'intent': 'clarify',
                        'result_brief': str(payload['clarify'])[:200],
                        'latency_ms': int((time.time() - start) * 1000)})
            self._ask_reply(ask_format.reply_clarify(payload['clarify']),
                            self.channel_id, self.message_id)
            return
        fname = payload.get('function')
        func = by_name.get(fname)
        known = fname and any(f['name'] == fname for f in ask_catalog.ACTIVE_FUNCTIONS)
        if payload.get('unknown') or not fname or not known:
            # LLM 编造目录外函数名 → 不执行，按"超出范围"回答
            self.write({'state': 'nointent', 'intent': str(fname or '')[:80],
                        'latency_ms': int((time.time() - start) * 1000)})
            self._ask_reply(ask_format.reply_nointent(), self.channel_id, self.message_id)
            return
        if not func:
            # 真实函数但提问人组不可见（防御 LLM 被诱导）→ 无权限
            self.write({'state': 'denied', 'intent': fname,
                        'latency_ms': int((time.time() - start) * 1000)})
            self._ask_reply(ask_format.reply_denied(), self.channel_id, self.message_id)
            return
        args = ask_catalog.sanitize_args(func['args'], payload.get('args'))
        try:
            model_obj = self.env[func['model']].with_user(asker).browse()
            data = getattr(model_obj, func['method'])(args)
        except AccessError:
            self.write({'state': 'denied', 'intent': fname,
                        'latency_ms': int((time.time() - start) * 1000)})
            self._ask_reply(ask_format.reply_denied(), self.channel_id, self.message_id)
            return
        except (UserError, ValueError) as e:
            self.write({'state': 'error', 'intent': fname,
                        'result_brief': str(e)[:200],
                        'latency_ms': int((time.time() - start) * 1000)})
            self._ask_reply(ask_format.reply_error(), self.channel_id, self.message_id)
            return
        body = ask_format.render_table(data)
        if self.channel_id and self.channel_id.channel_type == 'channel':
            body = body + Markup('<p style="color:#888">口径：提问人权限范围，结果频道可见</p>')
        self.write({
            'state': 'done', 'intent': fname,
            'result_brief': '%s：%s 行' % (data.get('title', fname), len(data.get('rows') or [])),
            'latency_ms': int((time.time() - start) * 1000),
        })
        msg = self._ask_reply(body, self.channel_id, self.message_id)
        if msg:
            self.write({'reply_message_id': msg.id})

    # ------------------------------------------------------------------
    # cron 兜底通道（ta_ask.async_mode）
    # ------------------------------------------------------------------
    def _cron_process_pending(self):
        pending = self.sudo().search([('state', '=', 'pending')], limit=20, order='id asc')
        for query in pending:
            try:
                query._ask_process()
            except Exception:
                _logger.exception('ta_ask cron 处理流水 %s 失败', query.id)
