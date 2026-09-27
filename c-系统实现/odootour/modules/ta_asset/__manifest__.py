# -*- coding: utf-8 -*-
{
    'name': '旅行社固定资产',
    'summary': '资产卡片台账、直线法残值率月折旧、自动生成折旧凭证（借折旧费/贷累计折旧）',
    'version': '20.0.1.0.0',
    'category': 'Travel Agency',
    'author': 'TMS Team',
    'depends': ['ta_finance'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_asset.xml',
        'data/ir_cron_depreciate.xml',
        'views/ta_asset_views.xml',
        'views/ta_asset_depreciation_views.xml',
        'views/res_config_settings_views.xml',
        'views/menuitems.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
