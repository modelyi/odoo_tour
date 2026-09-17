# -*- coding: utf-8 -*-
{
    'name': '增长官门户 (CMO)',
    'version': '19.0.1.0.0',
    'category': 'Tourism/Marketing',
    'summary': '首席增长官门户 - 营销分析与线索管理',
    'description': """
CMO 增长官门户
==============

功能特性
--------
* 营销概览仪表盘（营收汇总、渠道分布、CRM 漏斗、热门线路）
* CRM 线索管理（列表、详情、转团）
* 渠道分析报表
* 线路收客分析报表
* 客户地域分析报表
    """,
    'author': 'TMS Team',
    'website': 'https://www.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'website',
        'crm',
        'tour_order',
        'tour_product',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/portal_templates.xml',
        'views/portal_pages.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
