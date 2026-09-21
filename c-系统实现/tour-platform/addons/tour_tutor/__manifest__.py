# -*- coding: utf-8 -*-
{
    'name': 'TMS Tutor - 产品导览与角色菜单预览',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '产品展示 + 项目总结 + 角色菜单预览（仅超级用户）',
    'description': """
        TMS Tutor（产品导览）
        ====================
        面向超级用户（admin）的产品展示与项目总结「导览」应用，不建业务模型，
        纯 QWeb + Controller 实现：

        1. 产品导览文档（/tutor）
           - 产品概览（TMS 是什么、技术底座 Odoo 19）
           - 功能模块清单（9 个 tour_* 模块：名称/职责/关键模型/菜单入口）
           - 产品路径（接单→计调→资源安排→收款→财务核算→分佣→报表）
           - 项目总结（已交付里程碑）

        2. 角色菜单预览（/tutor/menus）
           - 6 个角色切换（超级用户/经理/计调/财务/销售/导游管理）
           - 按角色组 all_implied_ids 过滤，动态渲染 menu_tms_root 下
             7 个顶级菜单 + 各自子菜单，每个菜单可点击跳转对应功能

        安全：所有路由 auth='user' 且强制 user._is_superuser() 校验，
        仅超级用户可访问；只读展示 ir.ui.menu / ir_ui_menu_group_rel 元数据。
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'tour_base',
        'tour_product',
        'tour_order',
        'tour_operation',
        'tour_resource',
        'tour_shopping',
        'tour_accounting',
        'tour_report',
        'tour_website',
    ],
    'data': [
        'views/menu.xml',
        'views/tutor_templates.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
