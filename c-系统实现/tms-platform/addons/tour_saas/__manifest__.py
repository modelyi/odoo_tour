{
    "name": "TMS SaaS 租户管理",
    "version": "19.0.1.0.0",
    "summary": "SaaS 多租户模式：订阅控制、用户限额、租户隔离",
    "description": """
TMS SaaS 租户管理
=================

本模块实现 SaaS 多租户模式的核心功能：

* ``saas.suspended`` — 订阅暂停时关闭公开网站，后台保持可用
* ``saas.limit_users`` — 用户数量限制（0=无限制）

特性：
- 即时生效，无需卸载模块
- 租户友好的错误提示
- 与 TMS 系统深度集成
""",
    "author": "TMS Team",
    "website": "https://tms.solepro.cloud",
    "license": "LGPL-3",
    "category": "Tourism/SaaS",
    "depends": ["website"],
    "data": ["views/templates.xml"],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
}
