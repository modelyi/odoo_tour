# -*- coding: utf-8 -*-
"""DeepSeek Chat 封装：只允许返回 JSON 对象；永不接收/生成 SQL。

测试通过 mock 本模块的 ``requests.post`` 注入假响应。
"""
import json
import logging

import requests

_logger = logging.getLogger(__name__)


class AskLLMError(Exception):
    """LLM 调用失败或输出不可解析（统一收敛为此异常）。"""


def chat_json(api_key, base_url, model, messages, timeout=12.0):
    """调用 DeepSeek /chat/completions，要求 JSON 输出，返回解析后的 dict。

    仅对 timeout/连接错误/5xx 重试一次；4xx 直接失败（不重试以防放大）。
    """
    if not api_key:
        raise AskLLMError('DeepSeek API Key 未配置（设置 → 旅行社管理 → 问数机器人）')
    url = (base_url or 'https://api.deepseek.com/v1').rstrip('/') + '/chat/completions'
    payload = {
        'model': model or 'deepseek-chat',
        'messages': messages,
        'temperature': 0,
        'response_format': {'type': 'json_object'},
    }
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % api_key}
    last_error = None
    for _attempt in range(2):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=(3.05, timeout))
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            continue
        if resp.status_code >= 500:
            last_error = 'HTTP %s' % resp.status_code
            continue
        if resp.status_code != 200:
            # 不把响应体原文抛出，避免敏感内容进入日志/流水
            raise AskLLMError('DeepSeek 返回 HTTP %s' % resp.status_code)
        try:
            content = resp.json()['choices'][0]['message']['content']
            data = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise AskLLMError('LLM 输出不是合法 JSON: %s' % e)
        if not isinstance(data, dict):
            raise AskLLMError('LLM 输出不是 JSON 对象')
        return data
    raise AskLLMError('DeepSeek 调用失败: %s' % last_error)
