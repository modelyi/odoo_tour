# -*- coding: utf-8 -*-
{
    'name': 'TMS Base - 旅行社技术基础设施',
    'version': '19.0.0.3.0',
    'category': 'Travel/TMS',
    'summary': '旅行社基础设施：根菜单、银行账户、加密工具、配置、权限组、共享常量',
    'description': """
        TMS Base Module
        ================
        旅行社管理系统（TMS）的技术基础设施模块，承载所有 tour_* 模块共用的
        入口、工具与配置，是依赖链的最底层（仅依赖 base/mail，不依赖任何 tour 模块）：

        - 根菜单「旅行社管理」(menu_tms_root)，各业务模块菜单统一挂载于此
        - 敏感字段落盘加密工具（AES-256-GCM）：field_crypto + tour.encrypted.field.mixin
        - 系统配置 res.config.settings（默认币种、默认付款条件、导游默认分成比例、
          敏感数据查看组等系统级参数）
        - 基础安全组（旅行社用户 / 旅行社经理 / 敏感数据完整值查看组）
        - 共享 Selection 常量（BIZ_MODE 12 种业务模式、SUP_TYPE 供应商类型等）
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/tour_base_security.xml',
        'views/tour_dashboard_views.xml',
        'views/menu.xml',
        'views/res_config_settings_views.xml',
        'views/tour_bank_account_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'tour_base/static/src/scss/tour_dashboard.scss',
            'tour_base/static/src/xml/tour_dashboard.xml',
            'tour_base/static/src/js/tour_dashboard.js',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
