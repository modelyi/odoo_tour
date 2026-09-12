# -*- coding: utf-8 -*-
{
    'name': 'TMS Operation - 计调操作',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '旅行社计调操作：通用预订（派导/派车/订房/订餐/门票）',
    'description': """
        TMS Operation Module
        ====================
        旅行社计调操作模块（对应 BS-03 计调操作 v2.0）：
        - 通用预订 (tour.booking) 统一承载派导/派车/订房/订餐/门票 5 类资源调度
        - 资源类型用 selection 区分（guide/vehicle/hotel/meal/scenic）
        - 导游/车辆日期区间冲突检测（不同团、非取消、区间重叠阻止）
        - 金额按类型公式自动计算、车辆座位预警、用房/门票二次确认
        - 出团前置校验（tour.plan.action_start 联动）
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'tour_base', 'tour_resource', 'tour_order'],
    'data': [
        'security/tour_operation_security.xml',
        'security/ir.model.access.csv',
        'data/tour_booking_sequence.xml',
        'views/tour_booking_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
