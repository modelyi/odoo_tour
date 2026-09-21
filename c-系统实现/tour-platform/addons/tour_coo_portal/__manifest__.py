# -*- coding: utf-8 -*-
{
    'name': 'COO 门户',
    'version': '19.0.1.0.0',
    'category': 'Tourism/Operations',
    'summary': '首席运营官门户 - 运营监控与审批',
    'description': """
COO 运营门户
============

功能特性
--------
* 运营概览仪表盘
* 订单管线监控
* 资源调度看板
* 供应商总览
* 运营审批管理
    """,
    'author': 'TMS Team',
    'website': 'https://www.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'website',
        'tour_operation',
        'tour_resource',
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
