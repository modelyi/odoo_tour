# -*- coding: utf-8 -*-
{
    'name': 'TMS Resource - 资源管理',
    'version': '19.0.0.6.0',
    'category': 'Travel/TMS',
    'summary': '旅行社资源管理：导游、供应商、购物协议',
    'description': """
        TMS Resource Module
        ===================
        旅行社资源管理模块：
        - 导游档案 (tour.guide)
        - 供应商档案 (tour.supplier)
        - 购物协议 (tour.shop.agreement)
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'contacts', 'hr', 'tour_base', 'tour_product'],
    'data': [
        'security/ir.model.access.csv',
        'views/tour_guide_views.xml',
        'views/tour_supplier_views.xml',
        'views/tour_shop_agreement_views.xml',
        'views/hr_employee_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
