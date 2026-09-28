# -*- coding: utf-8 -*-
{
    'name': '旅行社导游借款与报账',
    'summary': '导游借款-发放-报账审核-佣金结算与税后净额冲抵借款（BS-08）',
    'version': '20.0.0.1.0',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_dispatch'],
    'data': [
        'security/ir.access.csv',
        'views/ta_guide_loan_views.xml',
        'views/ta_guide_expense_views.xml',
        'views/ta_guide_commission_views.xml',
        'views/ta_guide_performance_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
