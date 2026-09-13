# -*- coding: utf-8 -*-
{
    'name': 'TMS Product - 旅行社产品管理',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '旅行社管理系统产品模块：线路、分类、发团计划',
    'description': """
        TMS Product Module
        ==================
        旅行社管理系统的产品数据模型：
        - 线路分类 (tour.line.type)
        - 线路产品 (tour.line)
        - 发团计划 (tour.departure.plan)
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'product', 'tour_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/tour_line_views.xml',
        'views/tour_departure_views.xml',
        'views/tour_line_detail_views.xml',
        'views/tour_base_data_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/tour_base_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
