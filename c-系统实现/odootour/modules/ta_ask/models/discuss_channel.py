# -*- coding: utf-8 -*-
"""Discuss 接入：频道 @bot 或私聊 bot，消息即进入问数流水。

批2（问数 2.0）：多机器人——@ 到的是哪位 bot（通用/财务问数/导游问数），
就由该 bot 的目录回答并以该 bot 身份回帖；权限口径永远是提问人。
"""
import logging

from odoo import models

from . import ask_bots

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _message_post_after_hook(self, message):
        res = super()._message_post_after_hook(message)
        # 问数处理任何异常都不允许影响消息发送本身
        try:
            self._ta_ask_try_handle(message)
        except Exception:
            _logger.exception('ta_ask: 问数挂接异常（消息已正常发送）')
        return res

    def _ta_ask_try_handle(self, message):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        if not icp.get_bool('ta_ask.enabled'):
            return
        if message.message_type != 'comment':
            return
        # 问数 2.0：多 bot——找到命中的已注册 bot（@ 到谁 / 私聊里有谁）
        bots = ask_bots.registered_bots(self.env)
        if not bots:
            return
        bot_partners = [user.partner_id for _spec, user in bots]
        if message.author_id and message.author_id in bot_partners:
            return  # bot 自己的回帖（防递归）
        if self.channel_type == 'chat':
            member_partners = self.channel_member_ids.partner_id
            hit = next(((spec, user) for spec, user in bots
                        if user.partner_id in member_partners), None)
        elif self.channel_type == 'channel':
            hit = next(((spec, user) for spec, user in bots
                        if user.partner_id in message.partner_ids), None)
        else:
            return
        if not hit:
            return  # 未 @ 到任何问数 bot
        spec, bot_user = hit
        from .ta_ask_query import html_to_text
        question = html_to_text(message.body)
        if not question:
            return
        asker = message.author_id.user_ids.filtered('active')[:1]
        if not asker:
            return  # 提问者须是对应内部用户，按提问人权限执行
        query = self.env['ta.ask.query'].sudo().create({
            'asker_id': asker.id,
            'channel_id': self.id,
            'message_id': message.id,
            'question': question,
            'company_id': asker.company_id.id or self.env.company.id,
            'bot_code': spec['code'],
            'bot_user_id': bot_user.id,
        })
        query._ask_process()
