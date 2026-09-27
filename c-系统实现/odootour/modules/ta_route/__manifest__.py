{
    'name': '旅行社线路与发团计划',
    'summary': '线路产品、多价格体系、发团计划（发团计划）、并团',
    'version': '20.0.0.1.0',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_base'],
    'data': [
        'security/ir.access.csv',
        'views/ta_route_views.xml',
        'views/ta_departure_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
