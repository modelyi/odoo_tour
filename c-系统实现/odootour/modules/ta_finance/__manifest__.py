{
    'name': '旅行社收款认领',
    'summary': '收款登记-认领-审核三步闭环，审核后落凭证并核销订单应收',
    'version': '20.0.0.1.0',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_order', 'account'],
    'data': [
        'security/ir.access.csv',
        'security/ta_finance_groups.xml',
        'views/ta_bank_line_views.xml',
        'views/ta_payment_claim_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
