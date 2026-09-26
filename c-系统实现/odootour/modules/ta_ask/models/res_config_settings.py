# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ta_ask_enabled = fields.Boolean(
        string='启用 Discuss 问数机器人', config_parameter='ta_ask.enabled', default=False)
    ta_ask_deepseek_api_key = fields.Char(
        string='DeepSeek API Key', config_parameter='ta_ask.deepseek_api_key')
    ta_ask_deepseek_model = fields.Char(
        string='DeepSeek 模型', config_parameter='ta_ask.deepseek_model',
        default='deepseek-chat')
    ta_ask_deepseek_base_url = fields.Char(
        string='DeepSeek Base URL', config_parameter='ta_ask.deepseek_base_url',
        default='https://api.deepseek.com/v1')
    ta_ask_timeout = fields.Float(
        string='LLM 超时（秒）', config_parameter='ta_ask.timeout', default=12.0)
    ta_ask_async_mode = fields.Boolean(
        string='异步模式（cron 消费队列）', config_parameter='ta_ask.async_mode', default=False)
