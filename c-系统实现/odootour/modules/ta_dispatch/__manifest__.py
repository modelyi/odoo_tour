# -*- coding: utf-8 -*-
{
    'name': '旅行社计调派工',
    'summary': '单团资源派工（车/房/餐/票/地接/导游领队）、确认生成供应商账单、单团核算（BS-19）',
    'version': '20.0.0.1.0',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_order', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/ta_dispatch_views.xml',
        'views/ta_team_pnl_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
