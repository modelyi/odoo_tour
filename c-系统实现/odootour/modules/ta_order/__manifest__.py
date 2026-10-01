{
    'name': '旅行社订单报名',
    'summary': '团队/散客订单、名单、报价与应收计划',
    'version': '20.0.0.1.1',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_route'],
    'data': [
        'security/ir.access.csv',
        'views/ta_order_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
