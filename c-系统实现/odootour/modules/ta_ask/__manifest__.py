# -*- coding: utf-8 -*-
{
    'name': '旅行社 Discuss 问数机器人',
    'summary': '财务/CEO 通过 Discuss 自然语言问数：LLM 仅做白名单函数映射，查询按提问人权限执行；'
               '支持领域机器人（财务问数 / 导游问数）',
    'version': '20.0.2.0',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_guide', 'ta_finance', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/ask_bot_data.xml',
        'views/res_config_settings_views.xml',
        'views/ta_ask_query_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
