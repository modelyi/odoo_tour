# -*- coding: utf-8 -*-
{
    'name': 'TMS Report - 报表中心',
    'version': '19.0.0.2.0',
    'category': 'Travel/TMS',
    'summary': '旅行社报表中心：单团利润、导游业绩、购物返佣、每日收支',
    'description': """
        TMS Report Module
        =================
        旅行社报表中心模块（对应 SOUL 模块清单 tour_report）：
        - 单团利润报表 — 基于 tour.plan.account 单团核算（收入/成本/利润/利润不含购物）
        - 导游业绩报表 — 基于 tour.commission 佣金（佣金总额/导游税前分成/奖金/代扣个税/实发/留存）
        - 购物返佣报表 — 基于 tour.shop.record 购物记录（购物金额/返佣比例/返佣金额）
        - 每日收支报表 — 基于 tour.payment.claim 收款（收款金额/已使用/余额/手续费）

        实现方式（不引入第三方报表引擎）：
        - tour.report.wizard（TransientModel 报表向导）：选日期范围 + 报表类型 + 分组方式
        - 复用 Odoo 原生 pivot/graph 视图做分析，按团/导游/购物店/日 分组
        - 菜单挂「旅行社管理」下「报表中心」
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'tour_base', 'tour_product', 'tour_resource', 'tour_order',
                'tour_accounting', 'tour_shopping'],
    'data': [
        'security/ir.model.access.csv',
        'views/tour_report_wizard_views.xml',
        'views/tour_report_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
