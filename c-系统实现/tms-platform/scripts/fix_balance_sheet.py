#!/usr/bin/env python3
"""修复资产负债表：创建权益类科目、所有者权益报表板块，移动本年利润"""

import sys
import odoo
from odoo.tools import config

# 解析配置
config.parse_config(['-d', 'tms', '-c', '/etc/odoo/odoo.conf', '--stop-after-init', '--without-demo=False'])

# 初始化 Odoo
odoo.service.server.start(preload=[], stop=True)

# 获取数据库游标
db = odoo.sql_db.db_connect('tms')
with db.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

    print("=" * 60)
    print("步骤 0: 检查当前状态")
    print("=" * 60)

    # 检查权益类科目
    existing = env['account.account'].search([('code', 'in', ['4101', '4102', '4104'])])
    print(f"已存在的权益类科目: {existing.mapped(lambda r: r.code + ' ' + r.name)}")

    # 检查资产负债表
    balance_sheet = env['account.financial.report'].search([('name', 'like', '资产负债表')], limit=1)
    if balance_sheet:
        print(f"资产负债表: {balance_sheet.name}, ID: {balance_sheet.id}")
        lines = env['account.financial.report'].search([('parent_id', 'child_of', balance_sheet.id)], order='sequence')
        for line in lines:
            indent = '  ' * line.level
            print(f"  {indent}{line.name} (ID:{line.id}, 级别:{line.level}, 类型:{line.type}, 父级:{line.parent_id.name})")
    else:
        print("未找到资产负债表!")

    # 检查利润相关
    profit_reports = env['account.financial.report'].search([('name', 'like', '利润')])
    for p in profit_reports:
        print(f"利润相关: {p.name}, ID:{p.id}, 父级:{p.parent_id.name} (ID:{p.parent_id.id})")

    # 检查所有者权益
    equity_reports = env['account.financial.report'].search([('name', 'like', '所有者权益')])
    for e in equity_reports:
        print(f"权益报表: {e.name}, ID:{e.id}, 父级:{e.parent_id.name}")

    print()
    print("=" * 60)
    print("步骤 1: 创建缺失的权益类科目")
    print("=" * 60)

    accounts_to_create = [
        ('4101', '资本公积', 'equity'),
        ('4102', '盈余公积', 'equity'),
        ('4104', '利润分配——未分配利润', 'equity'),
    ]

    for code, name, account_type in accounts_to_create:
        existing_acc = env['account.account'].search([('code', '=', code)], limit=1)
        if existing_acc:
            print(f"  科目 {code} {name} 已存在 (ID: {existing_acc.id})，跳过")
        else:
            # 需要找到公司
            company = env.ref('base.main_company')
            new_acc = env['account.account'].create({
                'code': code,
                'name': name,
                'account_type': account_type,
                'company_id': company.id,
            })
            print(f"  创建科目 {code} {name} (ID: {new_acc.id})")

    cr.commit()
    print("  权益类科目处理完成")

    print()
    print("=" * 60)
    print("步骤 2: 创建所有者权益报表板块")
    print("=" * 60)

    if not balance_sheet:
        print("  错误: 未找到资产负债表，无法继续")
    else:
        equity_sum = env['account.financial.report'].search([
            ('name', 'like', '所有者权益'),
            ('parent_id', '=', balance_sheet.id)
        ], limit=1)

        if equity_sum:
            print(f"  所有者权益板块已存在 (ID: {equity_sum.id})，跳过")
        else:
            equity_sum = env['account.financial.report'].create({
                'name': '所有者权益',
                'sequence': 2,
                'parent_id': balance_sheet.id,
                'display_detail': 'no_detail',
                'type': 'sum',
            })
            print(f"  创建所有者权益汇总节点 (ID: {equity_sum.id})")

            # 创建权益明细节点
            equity_type = env.ref('account.data_account_type_equity', raise_if_not_found=False)
            if equity_type:
                env['account.financial.report'].create({
                    'name': '权益',
                    'parent_id': equity_sum.id,
                    'display_detail': 'detail_with_hierarchy',
                    'type': 'account_type',
                    'account_type_ids': [(6, 0, [equity_type.id])],
                })
                print("  创建权益明细节点")
            else:
                print("  警告: 未找到 equity 账户类型引用")

            cr.commit()
            print("  所有者权益板块创建完成")

    print()
    print("=" * 60)
    print("步骤 3: 移动'报告利润（亏损）'到所有者权益下")
    print("=" * 60)

    if not balance_sheet:
        print("  错误: 未找到资产负债表，无法继续")
    else:
        equity_sum = env['account.financial.report'].search([
            ('name', 'like', '所有者权益'),
            ('parent_id', '=', balance_sheet.id)
        ], limit=1)

        # 搜索"报告利润"
        profit_loss = env['account.financial.report'].search([('name', 'like', '报告利润')], limit=1)
        if not profit_loss:
            # 尝试其他名称
            profit_loss = env['account.financial.report'].search([('name', 'like', '利润')], limit=1)

        if profit_loss and equity_sum:
            old_parent = profit_loss.parent_id
            if old_parent.id != equity_sum.id:
                profit_loss.parent_id = equity_sum.id
                cr.commit()
                print(f"  已将 '{profit_loss.name}' (ID:{profit_loss.id}) 从 '{old_parent.name}' (ID:{old_parent.id}) 移动到 '所有者权益' (ID:{equity_sum.id})")
            else:
                print(f"  '{profit_loss.name}' 已在所有者权益下，无需移动")
        elif not profit_loss:
            print("  未找到'报告利润'报表项")
        elif not equity_sum:
            print("  未找到所有者权益汇总节点")

    print()
    print("=" * 60)
    print("步骤 4: 验证修复结果")
    print("=" * 60)

    # 重新读取资产负债表
    balance_sheet = env['account.financial.report'].search([('name', 'like', '资产负债表')], limit=1)
    if balance_sheet:
        lines = env['account.financial.report'].search([('parent_id', 'child_of', balance_sheet.id)], order='sequence')
        print("\n资产负债表最终结构:")
        for line in lines:
            indent = '  ' * line.level
            print(f"  {indent}{line.name} (ID:{line.id}, 级别:{line.level}, 类型:{line.type})")

    # 验证权益类科目
    equity_accounts = env['account.account'].search([('code', 'in', ['4101', '4102', '4104'])])
    print(f"\n权益类科目: {equity_accounts.mapped(lambda r: r.code + ' ' + r.name)}")

    cr.commit()
    print("\n修复完成!")
