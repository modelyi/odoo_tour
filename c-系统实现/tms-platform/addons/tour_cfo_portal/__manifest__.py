# -*- coding: utf-8 -*-
{
    'name': 'CFO 门户',
    'version': '19.0.1.0.0',
    'category': 'Tourism/Financial',
    'summary': '首席财务官门户 - 财务审批与监控',
    'description': """
CFO 财务门户
============

功能特性
--------
* 财务概览仪表盘
* 报账审批管理
* 佣金审批管理
* 借款审批管理
* 财务报表查看
* 资金流向监控
    """,
    'author': 'TMS Team',
    'website': 'https://www.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'website',
        'tour_accounting',
        'tour_order',
        'tour_resource',
        'hr_expense',
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
