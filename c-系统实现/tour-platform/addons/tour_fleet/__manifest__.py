# -*- coding: utf-8 -*-
{
    'name': 'TMS Fleet - 车队管理',
    'version': '19.0.1.1.0',
    'category': 'Travel/TMS',
    'summary': '旅行社车队管理：车辆、司机、调度',
    'description': """
        TMS Fleet Module
        ================
        基于 Odoo 原生 Fleet 模块扩展旅行社车队管理功能：
        - 车辆档案（座位数/加座数/所属车队/审核）
        - 司机档案（资质/结算/关联）
        - 旅行社车型分类
    """,
    'author': 'TMS Team',
    'website': 'https://www.solepro.cloud',
    'depends': [
        'fleet',
        'tour_resource',
        'tour_base',
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/fleet_data.xml',
        'views/tour_driver_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
