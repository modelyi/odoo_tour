# -*- coding: utf-8 -*-
{
    'name': 'TMS Operation - 计调操作',
    'version': '19.0.0.6.0',
    'category': 'Travel/TMS',
    'summary': '旅行社计调操作：7 类资源预订（派导/派车/订房/订餐/门票/保险/地接）+ 计调看板',
    'description': """
        TMS Operation Module
        ====================
        旅行社计调操作模块（对应 BS-03 计调操作 v2.0）：
        - 计调已 project.task 化：一预订一 task，project.project 1:1 团（共享 analytic）
        - 资源类型用 selection 区分（guide/vehicle/hotel/meal/scenic）
        - 导游/车辆日期区间冲突检测（不同团、非取消、区间重叠阻止）
        - 金额按类型公式自动计算、车辆座位预警、用房/门票二次确认
        - 出团前置校验（tour.plan.action_start 查 project.task）
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'project', 'tour_base', 'tour_product',
                'tour_resource', 'tour_order', 'fleet', 'tour_fleet'],
    'data': [
        'security/tour_operation_security.xml',
        'data/sequence.xml',
        'views/project_task_views.xml',
        'views/tour_plan_project_views.xml',
        'views/booking_kanban_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
