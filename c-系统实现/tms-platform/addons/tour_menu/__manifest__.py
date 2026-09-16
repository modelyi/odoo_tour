# -*- coding: utf-8 -*-
{
    'name': 'TMS 菜单结构',
    'version': '19.0.0.1.0',
    'category': 'Tourism/TMS',
    'summary': 'TMS 系统菜单结构（依赖所有业务模块）',
    'description': """
TMS 菜单结构
============

本模块定义 TMS 系统的完整菜单结构，依赖所有业务模块以确保 action 引用正确。

从 tour_base 分离出来，解决模块安装顺序导致的 action 引用问题。
""",
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'tour_base',
        'tour_product',
        'tour_order',
        'tour_operation',
        'tour_resource',
        'tour_shopping',
        'tour_report',
        'tour_accounting',
    ],
    'data': [
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
