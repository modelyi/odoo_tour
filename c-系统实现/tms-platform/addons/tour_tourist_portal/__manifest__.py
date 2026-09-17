# -*- coding: utf-8 -*-
{
    'name': '游客门户',
    'version': '19.0.1.0.0',
    'category': 'Tourism',
    'summary': '游客门户 - 订单查看、付款进度、行程管理与发票',
    'description': """
游客门户
========

功能特性
--------
* 游客注册与登录
* 我的订单查看（报名记录、客人名单、金额明细）
* 付款进度跟踪
* 即将出行行程查看
* 发票管理
    """,
    'author': 'TMS Team',
    'website': 'https://www.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'website',
        'tour_website',
        'tour_order',
        'tour_accounting',
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
