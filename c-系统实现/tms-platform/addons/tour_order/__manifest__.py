# -*- coding: utf-8 -*-
{
    'name': 'TMS Order - 订单管理',
    'version': '19.0.0.3.0',
    'category': 'Travel/TMS',
    'summary': '旅行社订单管理：团队订单、报名、并团、单团变更',
    'description': """
        TMS Order Module
        ================
        旅行社订单管理模块（对应 BS-02 订单管理 v2.0）：
        - 团队订单 / 发团计划 (tour.plan)
        - 订单报名 (tour.plan.reg)
        - 并团记录 (tour.merge)
        - 单团变更记录 (tour.plan.change)

        核心业务：
        - 业务模式 BizMode 12 种（DT/DSK/DSS/DSN/流转/产品计划/关键字并团/DTO/DSO/DD/自由行/共享协议）
        - 散客并团靠 first_plan_id（非 main_reg_id），main_reg_id 仅自由行 51/52 使用
        - 金额字段 5 类：报价/收款/未收/退款/代收代付
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'contacts', 'crm', 'tour_base', 'tour_product',
                'tour_resource'],
    'data': [
        'security/ir.model.access.csv',
        'security/tour_crm_security.xml',
        'data/tour_plan_crm_sequence.xml',
        'views/tour_plan_views.xml',
        'views/crm_lead_views.xml',
        'views/tour_plan_reg_views.xml',
        'views/tour_merge_views.xml',
        'views/tour_plan_change_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
