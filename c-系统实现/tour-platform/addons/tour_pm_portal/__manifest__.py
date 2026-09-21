{
    'name': '产品专家门户',
    'version': '19.0.1.0.0',
    'category': 'Tourism/Portal',
    'summary': '线路产品经理门户——线路管理、班期监控、业绩分析',
    'description': """
产品专家门户（Product Manager Portal）
======================================
面向线路产品经理的自助门户，提供：
- 产品仪表盘：线路/班期/收入全局健康度 + 预警
- 线路总览：全部线路产品的管理视图
- 线路详情：单线路完整档案 + 12 月趋势
- 班期管理：班期售罄率监控
- 产品业绩分析：线路排行 + 目的地 + 利润率
    """,
    'author': 'TMS Team',
    'website': 'https://www.solepro.cloud',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'website',
        'tour_product',
        'tour_order',
        'tour_resource',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/portal_templates.xml',
        'views/portal_pages.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'tour_pm_portal/static/src/pm_portal.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
