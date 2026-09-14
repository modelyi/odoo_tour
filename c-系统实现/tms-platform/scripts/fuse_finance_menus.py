# -*- coding: utf-8 -*-
"""融合旅行社财务菜单进 Odoo accounting 入口（一次性迁移脚本）。

运行方式（在 tms-platform 目录）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < scripts/fuse_finance_menus.py

效果：
  1. 财务角色 group_tour_finance 隐含 account.group_account_user（可见 accounting 入口 + 会计/审查/报表分组）
  2. 新建「旅行社财务」分组菜单（parent=accounting, seq=30，报表之后、配置之前）
  3. 9 个业务财务菜单 + 财务配置(银行账户/支付渠道/结算方式) 挂到「旅行社财务」，逐个设 group_tour_finance
  4. 11 个标准会计菜单归位回 accounting 对应分组（发票→客户；损益/资产负债/试算/现金流→报表；
     往来账龄→往来单位报告；催款级别→审查；催款报告→客户；定期开票/资产→会计）
  5. 删除中间层菜单 财务会计(624) / 财务管理(268)，先删 ir_model_data 再删菜单
"""
from odoo import api

Menu = env['ir.ui.menu']
IMD = env['ir.model.data']

FIN = env.ref('tour_base.group_tour_finance')          # 102 财务
ACC_TOP = env.ref('account.menu_finance')              # 151 财务(accounting)
GRP_CUSTOMER = env.ref('account.menu_finance_receivables')   # 153 客户
GRP_ACCT = env.ref('account.menu_finance_entries')     # 165 会计
GRP_REVIEW = env.ref('account.account_audit_menu')     # 170 审查
GRP_REPORT = env.ref('account.menu_finance_reports')   # 174 报表
GRP_PARTNER_REPORT = env.ref('tour_accounting.account_reports_partner')  # 479 往来单位报告

log = []
def say(*a):
    log.append(' '.join(str(x) for x in a))

# ---- 1) 财务角色隐含 Accountant ----
acct_user = env.ref('account.group_account_user')  # 26
if acct_user.id not in FIN.implied_ids.ids:
    FIN.write({'implied_ids': [(4, acct_user.id)]})
    say('imply account.group_account_user(%s) -> %s' % (acct_user.id, FIN.id))
else:
    say('skip imply (already present)')

# ---- 2) 新建「旅行社财务」分组菜单 ----
NEW_XMLID = 'tour_accounting.menu_tour_finance'
existing = IMD.search([('module', '=', 'tour_accounting'), ('name', '=', 'menu_tour_finance'),
                       ('model', '=', 'ir.ui.menu')], limit=1)
if existing:
    new_group = Menu.browse(existing.res_id)
    new_group.write({'parent_id': ACC_TOP.id, 'sequence': 30})
    say('reuse existing menu_tour_finance id=%s' % new_group.id)
else:
    new_group = Menu.create({
        'name': '旅行社财务',
        'parent_id': ACC_TOP.id,
        'sequence': 30,
        'group_ids': [(6, 0, [FIN.id])],
    })
    IMD.create({'module': 'tour_accounting', 'name': 'menu_tour_finance',
                'model': 'ir.ui.menu', 'res_id': new_group.id, 'noupdate': False})
    say('create menu_tour_finance id=%s' % new_group.id)

# 确保新分组 group_ids 含财务角色
new_group.write({'group_ids': [(4, FIN.id)]})

# ---- 3) 9 业务财务菜单 + 财务配置 → 旅行社财务，逐个设 group_tour_finance ----
biz = [
    ('tour_accounting.menu_tour_payment_claim',     10),   # 272 收款登记/认领
    ('tour_accounting.menu_tour_pay_request',       15),   # 643 请款单
    ('tour_accounting.menu_tour_reconciliation',    20),   # 273 对账
    ('tour_accounting.menu_tour_commission',        30),   # 274 佣金
    ('tour_accounting.menu_tour_plan_account',      40),   # 271 单团核算
    ('tour_accounting.menu_tour_guide_loan',        45),   # 644 导游借款
    ('tour_accounting.menu_tour_guide_real_pay',    46),   # 645 导游报账
    ('tour_accounting.menu_tour_dunning',           50),   # 622 团款催收台账
    ('tour_accounting.menu_tour_plan_account_aging', 60),  # 623 团款应收账龄分析
]
for xmlid, seq in biz:
    m = env.ref(xmlid)
    m.write({'parent_id': new_group.id, 'sequence': seq, 'group_ids': [(4, FIN.id)]})
    say('biz %s(%s) -> 旅行社财务 seq=%s' % (xmlid, m.id, seq))

# 财务配置（627 及其子菜单）
cfg = env.ref('tour_accounting.menu_tms_finance_config')
cfg.write({'parent_id': new_group.id, 'sequence': 100, 'group_ids': [(4, FIN.id)]})
say('cfg menu_tms_finance_config(%s) -> 旅行社财务 seq=100' % cfg.id)
for xmlid in ('tour_accounting.menu_tour_bank_account',      # 269 银行账户
              'tour_accounting.menu_tour_pay_channel',       # 270 支付渠道
              'tour_product.menu_tour_pay_way'):             # 226 结算方式
    m = env.ref(xmlid)
    m.write({'group_ids': [(4, FIN.id)]})
    say('cfg-child %s(%s) group=财务' % (xmlid, m.id))

# ---- 4) 11 个标准会计菜单归位回 accounting ----
std = [
    ('account.menu_action_move_out_invoice_type',             GRP_CUSTOMER,       1),  # 154 发票
    ('tour_accounting.account_financial_reports_profit_loss', GRP_REPORT,        10),  # 489 损益表
    ('tour_accounting._account_financial_reports_balance_sheet', GRP_REPORT,     20),  # 490 资产负债表
    ('tour_accounting.menu_Balance_report',                   GRP_REPORT,        30),  # 494 试算平衡表
    ('tour_accounting.menu_account_cash_flow_report',         GRP_REPORT,        40),  # 497 现金流量表
    ('tour_accounting.menu_aged_trial_balance',               GRP_PARTNER_REPORT, 2),  # 495 往来账龄 → 往来单位报告
    ('tour_accounting.account_followup_menu',                 GRP_REVIEW,        30),  # 482 催款级别
    ('tour_accounting.customer_statements_menu',              GRP_CUSTOMER,      20),  # 483 催款报告
    ('tour_accounting.menu_account_recurring_invoice',        GRP_ACCT,          40),  # 504 定期开票
    ('tour_accounting.menu_action_account_asset_asset_form',  GRP_ACCT,          45),  # 486 资产
    ('tour_accounting.menu_action_asset_asset_report',        GRP_ACCT,          50),  # 501 资产报表
]
for xmlid, parent, seq in std:
    m = env.ref(xmlid)
    m.write({'parent_id': parent.id, 'sequence': seq})
    say('std %s(%s) -> %s(%s) seq=%s' % (xmlid, m.id, parent.id, parent.name, seq))

# ---- 5) 删除中间层：财务会计 624 / 财务管理 268（先删 ir_model_data）----
for xmlid in ('tour_accounting.menu_tour_finance_general',   # 624 财务会计
              'tour_accounting.menu_tms_finance'):           # 268 财务管理
    imd = IMD.search([('module', '=', 'tour_accounting'), ('name', '=', xmlid.split('.')[1]),
                      ('model', '=', 'ir.ui.menu')], limit=1)
    if imd:
        mid = imd.res_id
        imd.unlink()
        menu = Menu.browse(mid)
        if menu.exists():
            menu.unlink()
            say('delete %s (menu id=%s)' % (xmlid, mid))
        else:
            say('menu %s already gone' % xmlid)
    else:
        say('skip delete %s (no ir_model_data)' % xmlid)

env.cr.commit()
print('\n'.join(log))
print('DONE')
