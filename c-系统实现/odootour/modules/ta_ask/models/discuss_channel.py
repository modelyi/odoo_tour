# -*- coding: utf-8 -*-
import logging

from odoo import models

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
        bot = self.env.ref('ta_ask.res_user_ask_bot', raise_if_not_found=False)
        if not bot or message.author_id == bot.partner_id:
            return  # 开关未开 / bot 自己的回帖（防递归）
        if self.channel_type == 'chat':
            if bot.partner_id not in self.channel_member_ids.partner_id:
                return
        elif self.channel_type == 'channel':
            if bot.partner_id not in message.partner_ids:
                return  # 频道里只回答 @ 到 bot 的消息
        else:
            return
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
        })
        query._ask_process()
