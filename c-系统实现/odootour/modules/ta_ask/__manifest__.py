# -*- coding: utf-8 -*-
{
    'name': '旅行社 Discuss 问数机器人',
    'summary': '财务/CEO 通过 Discuss 自然语言问数：LLM 仅做白名单函数映射，查询按提问人权限执行',
    'version': '20.0.1.0',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_guide', 'mail'],
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
