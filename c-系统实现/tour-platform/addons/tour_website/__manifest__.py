# -*- coding: utf-8 -*-
{
    'name': 'TMS Website - B2C 线上销售',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '线路展示 + 散客在线报名（线下付款）',
    'description': """
        TMS Website - B2C 线上销售
        =========================
        B2C 散客线上销售最小闭环（BS-13 / TDS-B2C-001）：
        - 官网展示线路列表 / 详情 / 行程明细 / 班期余位（tour.line / tour.line.detail / tour.departure）
        - 无登录在线报名（create_online_reg 单一校验入口）→ 落库 tour.plan.reg + tour.plan
        - 报名回执（报名单号 / 应付金额 / 付款指引）
        - 线下付款（复用 tour.payment.claim，不另建收款流程）

        同时补齐 4 个模型缺口（按 TDS §2.1 决策：不修改 tour_product/tour_order，全部 _inherit 在本模块）：
        - GAP-1 tour.departure ↔ tour.plan 外键：tour.plan.departure_id + 报名时自动建团
        - GAP-2 tour.plan.reg.passenger 客人证件子表（id_number 加密存储）
        - GAP-3 from_type 新增 '6' 线上官网 渠道标识
        - GAP-4 tour.departure 补齐老人/学生/婴儿价（回退线路价）
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'website',
        'portal',
        'tour_base',
        'tour_product',
        'tour_order',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequences.xml',
        'data/website_brand.xml',
        'views/templates.xml',
        'views/homepage_templates.xml',
        'views/website_brand_templates.xml',
        'views/backend_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'tour_website/static/src/css/tour_website.css',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
