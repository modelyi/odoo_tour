{
    'name': '导游门户',
    'summary': '导游自助门户：派团查看、佣金查询、借款状态、报账提交',
    'version': '19.0.1.0.0',
    'category': 'Tourism',
    'author': 'TMS Team',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'website',
        'tour_resource',
        'tour_accounting',
        'tour_order',
        'hr_expense',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/mail_template.xml',
        'views/tour_guide_views.xml',
        'views/portal_templates.xml',
        'views/portal_pages.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'tour_guide_portal/static/src/css/guide_portal.css',
        ],
    },
    'installable': True,
    'application': False,
}
