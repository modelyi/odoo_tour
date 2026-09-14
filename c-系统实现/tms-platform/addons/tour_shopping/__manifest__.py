# -*- coding: utf-8 -*-
{
    'name': 'TMS Shopping - 购物管理',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '旅行社购物管理：团队购物记录',
    'description': """
        TMS Shopping Module
        ===================
        旅行社购物管理模块：
        - 购物记录 (tour.shop.record)：团队在购物店的消费明细
        - 购物返佣是团队利润来源，返佣金额 = 购物金额 × 返佣比例 / 100
        - 购物店档案使用 tour.supplier (sup_type=shop)
        - 购物协议复用 tour.shop.agreement（返佣比例来源）
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'tour_base', 'tour_product', 'tour_resource', 'tour_order', 'tour_accounting'],
    'data': [
        'security/ir.model.access.csv',
        'views/tour_shop_record_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
