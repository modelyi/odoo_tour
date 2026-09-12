# -*- coding: utf-8 -*-
{
    'name': 'TMS Base - 旅行社管理基础',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '旅行社管理系统基础模块：线路、分类、发团计划',
    'description': """
        TMS Base Module
        ===============
        旅行社管理系统的基础数据模型：
        - 线路分类 (tour.line.type)
        - 线路产品 (tour.line)
        - 发团计划 (tour.departure.plan)
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/tour_line_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/tour_base_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
