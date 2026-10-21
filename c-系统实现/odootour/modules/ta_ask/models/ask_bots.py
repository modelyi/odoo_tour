# -*- coding: utf-8 -*-
"""问数机器人注册表：通用助手 + 领域机器人（财务问数 / 导游问数）。

每个 bot 是一个独立 res.users（data/ask_bot_data.xml，noupdate）：
- 频道中 @ 到哪个 bot 就由哪个 bot 的目录回答；
- 私聊中把对应 bot 拉进会话即可；
- 目录仍按提问人组过滤（权限口径=提问人），bot 只决定"问什么领域"。
"""

ASK_BOTS = [
    {
        'xmlid': 'ta_ask.res_user_ask_bot',
        'code': 'general',
        'name': '问数助手',
        'intro': '通用问数助手：可查销售、财务、导游全目录中您有权限的数据。',
    },
    {
        'xmlid': 'ta_ask.res_user_finance_bot',
        'code': 'finance',
        'name': '财务问数',
        'intro': ('财务问数机器人：收款认领、应收与账龄、供应商付款、'
                  '费用报销、收入确认、单团毛利、计调成本。'),
    },
    {
        'xmlid': 'ta_ask.res_user_guide_bot',
        'code': 'guide',
        'name': '导游问数',
        'intro': ('导游问数机器人：导游绩效、借支余额、佣金与个税、'
                  '导游报账、景点毛利贡献。'),
    },
]

BY_CODE = {b['code']: b for b in ASK_BOTS}


def registered_bots(env):
    """返回已安装且存在的 bot res.users 记录列表（缺 ref 时跳过，便于独立装载）。"""
    bots = []
    for spec in ASK_BOTS:
        user = env.ref(spec['xmlid'], raise_if_not_found=False)
        if user and user.active:
            bots.append((spec, user))
    return bots


def bot_for_partner(env, partner):
    """按 partner 反查 bot 规格（找不到返回 None）。"""
    for spec, user in registered_bots(env):
        if user.partner_id == partner:
            return spec
    return None


def bot_user(env, code):
    spec = BY_CODE.get(code)
    if not spec:
        return None
    user = env.ref(spec['xmlid'], raise_if_not_found=False)
    return user if (user and user.active) else None
