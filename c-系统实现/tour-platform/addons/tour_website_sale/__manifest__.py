# -*- coding: utf-8 -*-
{
    'name': 'TMS Website Sale - 线路电商销售',
    'version': '19.0.0.1.0',
    'category': 'Travel/TMS',
    'summary': '线路 product 电商闭环：website_sale 下单 → sale.order 桥接 tour.plan.reg',
    'description': """
        TMS Website Sale - 线路电商销售（TDS-PROD-001 第二阶段）。

        - sale.order.line 扩展：departure_id（班期必选）+ 五档人数（成人/儿童/老人/学生/婴儿）
        - 商品页班期选择 + 人数填写，单价服务端重算，前端只读
        - 结账确认后桥接 tour.plan.reg/tour.plan（复用共享服务方法）
        - 与 create_online_reg 合并为共享服务方法，财务唯一口径在 tour.plan，sale.order 不独立出账
        - 线下付款（结账后订单待线下收款）
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'website_sale',
        'tour_product',
        'tour_order',
        'tour_website',
    ],
    'data': [
        'views/backend_views.xml',
        'views/product_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'tour_website_sale/static/src/css/tour_website_sale.css',
            'tour_website_sale/static/src/js/tour_website_sale.js',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
