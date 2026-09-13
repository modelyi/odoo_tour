# -*- coding: utf-8 -*-
{
    'name': 'TMS Finance - 财务管理',
    'version': '19.0.0.3.0',
    'category': 'Travel/TMS',
    'summary': '旅行社财务管理：银行账户、支付渠道、单团核算、收款认领、对账、佣金（含个税代扣）',
    'description': """
        TMS Finance Module
        ==================
        旅行社财务管理模块（对应 BS-05 财务管理 v2.0）：
        - 银行账户 (tour.bank.account) — 银行卡号加密存储（TODO）+ 掩码展示
        - 支付渠道 (tour.pay.channel) — 5 种：银行转账/微信/支付宝/现金/其他
        - 单团核算 (tour.plan.account) — 一团一核算，收入-成本=利润
        - 收款登记/认领 (tour.payment.claim) — 先收后认，双维度结算方式
        - 对账 (tour.reconciliation) — 11 类往来对账
        - 佣金 (tour.commission) — 导游分成 + 个税代扣（劳务报酬 20%-40%）

        关键业务：
        - 结算方式两维度：收付场景 (tour.pay.way) + 支付渠道 (tour.pay.channel)
        - 敏感字段银行卡号 BankAccountNo：字段已建 + 掩码展示，加密落盘留 TODO
        - 个税代扣：劳务报酬 20%-40% 累进预扣，实发 = 税前 - 预扣
    """,
    'author': 'SolePro',
    'website': 'https://tms.solepro.cloud',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'account', 'analytic',
                'tour_base', 'tour_resource', 'tour_order'],
    'data': [
        'security/tour_finance_security.xml',
        'security/ir.model.access.csv',
        'data/account_account_tour.xml',
        'data/tour_payment_claim_sequence.xml',
        'data/tour_commission_sequence.xml',
        'data/tour_reconciliation_sequence.xml',
        'data/tour_pay_channel_data.xml',
        'views/tour_bank_account_views.xml',
        'views/tour_pay_channel_views.xml',
        'views/tour_plan_views.xml',
        'views/tour_plan_account_views.xml',
        'views/tour_payment_claim_views.xml',
        'views/tour_reconciliation_views.xml',
        'views/tour_commission_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
