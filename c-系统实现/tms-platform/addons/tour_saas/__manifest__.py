{
    "name": "TMS SaaS 租户管理",
    "version": "19.0.2.0.0",
    "summary": "SaaS 多租户模式：租户数据库创建、订阅控制、用户限额",
    "description": """
TMS SaaS 租户管理
=================

核心功能：

* 租户数据库创建与管理（独立 PostgreSQL 数据库）
* ``saas.suspended`` — 订阅暂停时关闭公开网站，后台保持可用
* ``saas.limit_users`` — 用户数量限制（0=无限制）
* 参数同步 — 中央管理库推送配置到租户数据库

特性：
- 后台异步创建数据库，自动安装 TMS 全套模块
- 即时暂停/恢复，无需卸载模块
- 仅系统管理员可操作
""",
    "author": "TMS Team",
    "website": "https://tms.solepro.cloud",
    "license": "LGPL-3",
    "category": "Tourism/SaaS",
    "depends": ["website"],
    "data": [
        "security/ir.model.access.csv",
        "security/tour_saas_security.xml",
        "views/templates.xml",
        "views/tenant_views.xml",
        "views/tenant_menu.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
}
