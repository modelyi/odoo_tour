# -*- coding: utf-8 -*-
"""
财务三表报表配置修复脚本（幂等，可重复执行）

运行方式（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < fix_financial_reports.py

背景：base_accounting_kit（Cybrosys）的 account.financial.report 三表定义存在两处配置问题，
导致现金流量表为空、资产负债表节点 account_type_ids 语义错误：
  1. 现金流量表：经营现金流「Operations」节点（type=sum）未挂资金科目 account_ids，
     导致 Cash In/Cash Out 恒为 0。
  2. 资产负债表：Assets/Liability 节点 account_type_ids 误写为 income_other（复制模板残留）；
     实际报表引擎按节点名硬编码覆盖（见 wizard/financial_report.py 的 Assets/Liability 分支），
     故不影响取数，但语义错误，本脚本一并纠正。

修复动作：
  1. Operations 节点 account_ids ← 全部 asset_cash 资金科目（1001/1002/1012/…）。
  2. Assets 节点 account_type_ids ← asset_current；Liability 节点 ← liability_current。
"""
from odoo import fields


def main():
    FR = env['account.financial.report']

    # 1. 现金流量表：经营现金流节点挂资金科目
    operation = env.ref('tour_accounting.account_financial_report_operation0')
    cash_accounts = env['account.account'].search([('account_type', '=', 'asset_cash')])
    operation.write({'account_ids': [(6, 0, cash_accounts.ids)]})
    print('[cash-flow] operation.account_ids = %s' % [a.code for a in cash_accounts])

    # 2. 资产负债表：节点 account_type_ids 语义纠正（报表引擎按节点名覆盖，此处仅为语义正确）
    assets = env.ref('tour_accounting.account_financial_report_assets0')
    assets.write({'account_type_ids': 'asset_current'})
    liability = env.ref('tour_accounting.account_financial_report_liability0')
    liability.write({'account_type_ids': 'liability_current'})
    print('[balance-sheet] assets.account_type_ids=asset_current, liability=liability_current')

    env.cr.commit()
    print('========== 三表配置修复完成 ==========')
    print('现金流量表 Cash In/Out 数据源：%d 个资金科目' % len(cash_accounts))


if __name__ == '__main__':
    main()
