# -*- coding: utf-8 -*-
"""LLM Chat 封装（OpenAI 兼容端点）：只允许返回 JSON 对象；永不接收/生成 SQL。

provider 无关：任何 OpenAI 兼容网关均可接入——
- DeepSeek：https://api.deepseek.com/v1（sk-... Key，stream 两种皆可）
- CodeBuddy/WorkBuddy 网关：https://www.codebuddy.cn/v2（ck_... API Key，
  上游强制 stream=true，SSE 响应 data:{chunk}…data:[DONE]）

实现统一走流式请求 + SSE 解析（CodeBuddy 网关不支持非流式，
返回 400 "Non-stream chat request is currently not supported"）。

网关兼容性：部分网关不支持 response_format=json_object，
遇到 400 自动去掉该参数重试一次（仅一次，不放大请求）。

测试通过 mock 本模块的 ``requests.post`` 注入假响应（iter_lines 提供 SSE 行）。
"""
import json
import logging

import requests

_logger = logging.getLogger(__name__)


class AskLLMError(Exception):
    """LLM 调用失败或输出不可解析（统一收敛为此异常）。"""


def _parse_sse(resp):
    """解析 OpenAI 风格 SSE 流（iter_lines），拼接 delta.content。"""
    parts = []
    for raw in resp.iter_lines():
        if not raw:
            continue
        line = raw.decode('utf-8', errors='replace') \
            if isinstance(raw, bytes) else str(raw)
        if not line.startswith('data:'):
            continue
        data = line[len('data:'):].strip()
        if data == '[DONE]':
            break
        try:
            chunk = json.loads(data)
        except ValueError:
            continue
        choices = chunk.get('choices') or []
        if not choices:
            continue
        delta = choices[0].get('delta') or {}
        if delta.get('content'):
            parts.append(delta['content'])
    return ''.join(parts)


def chat_json(api_key, base_url, model, messages, timeout=12.0):
    """调用 /chat/completions（流式），要求 JSON 输出，返回解析后的 dict。

    仅对 timeout/连接错误/5xx 重试一次；4xx 直接失败（不重试以防放大），
    唯一例外：带 response_format 收到 400 时，去掉该参数重试一次。
    """
    if not api_key:
        raise AskLLMError('LLM API Key 未配置（设置 → 旅行社管理 → 问数机器人）')
    url = (base_url or 'https://api.deepseek.com/v1').rstrip('/') + '/chat/completions'
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % api_key}

    def _post(payload):
        # 传副本：降级重试会 pop payload 键，不能让两次调用共享同一 dict
        return requests.post(url, json=dict(payload), headers=headers,
                             timeout=(3.05, timeout))

    last_error = None
    for _attempt in range(2):
        payload = {
            'model': model or 'deepseek-chat',
            'messages': messages,
            'temperature': 0,
            'stream': True,  # CodeBuddy 网关强制流式；DeepSeek 亦兼容
            'response_format': {'type': 'json_object'},
        }
        try:
            resp = _post(payload)
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            continue
        if resp.status_code == 400:
            # 网关不认识 response_format（部分 OpenAI 兼容实现）：
            # 去掉后重试一次；仍 400 则原样报错
            payload.pop('response_format')
            try:
                resp = _post(payload)
            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                continue
        if resp.status_code >= 500:
            last_error = 'HTTP %s' % resp.status_code
            continue
        if resp.status_code != 200:
            # 不把响应体原文抛出，避免敏感内容进入日志/流水
            raise AskLLMError('LLM 服务返回 HTTP %s' % resp.status_code)
        content = _parse_sse(resp)
        try:
            data = json.loads(content)
        except ValueError as e:
            raise AskLLMError('LLM 输出不是合法 JSON: %s' % e)
        if not isinstance(data, dict):
            raise AskLLMError('LLM 输出不是 JSON 对象')
        return data
    raise AskLLMError('LLM 调用失败: %s' % last_error)
