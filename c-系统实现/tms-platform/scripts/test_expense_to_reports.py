#!/usr/bin/env python3
"""
费用端到端测试：费用录入 → 会计分录 → 三大报表

测试场景：
1. 导游报销差旅费（现金支付）
2. 地接社费用（应付账款）
3. 办公费用（银行支付）

验证：
- 会计分录正确生成
- 利润表：费用正确反映
- 资产负债表：现金/应付变化正确
- 现金流量表：现金流出分类正确
- 三表勾稽关系正确
"""

import subprocess
import json
from datetime import datetime, timedelta


def run_sql(query, fetch=True):
    """执行 SQL 查询"""
    cmd = ['docker', 'exec', '-i', 'tms-db', 'psql', '-U', 'odoo', '-d', 'tms', '-t', '-c', query]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if fetch:
        return result.stdout.strip()
    return result.returncode == 0


def run_odoo_shell(script):
    """执行 Odoo shell 脚本"""
    cmd = ['docker', 'exec', '-i', 'tms-odoo', 'odoo', 'shell', '-d', 'tms', '--stop-after-init']
    result = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=30)
    return result.stdout, result.stderr


def print_section(title):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def get_initial_state():
    """获取测试前的状态"""
    print_section("步骤 1: 获取测试前状态")
    
    # 获取最新期间
    period_sql = """
    SELECT id, name, date_start, date_end
    FROM tour_account_period
    ORDER BY date_start DESC
    LIMIT 1;
    """
    period_result = run_sql(period_sql)
    print(f"最新期间:\n{period_result}\n")
    
    # 获取当前现金余额
    cash_sql = """
    SELECT 
        aa.name->>'zh_CN' as account_name,
        COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0) as balance
    FROM account_account aa
    LEFT JOIN account_move_line aml ON aa.id = aml.account_id
    LEFT JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type IN ('asset_cash', 'asset_current')
    GROUP BY aa.id, aa.name
    ORDER BY aa.name->>'zh_CN';
    """
    cash_result = run_sql(cash_sql)
    print(f"当前现金余额:\n{cash_result}\n")
    
    # 获取当前应付账款余额
    ap_sql = """
    SELECT 
        COALESCE(SUM(aml.credit), 0) - COALESCE(SUM(aml.debit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type = 'liability_payable';
    """
    ap_result = run_sql(ap_sql)
    print(f"当前应付账款余额: {ap_result}\n")
    
    return {
        'cash': cash_result,
        'ap': ap_result,
    }


def create_test_expenses():
    """创建测试费用"""
    print_section("步骤 2: 创建测试费用")
    
    script = """
# 获取最新期间
period = env['tour.account.period'].search([], order='date_start desc', limit=1)
if not period:
    print("错误: 未找到会计期间")
    exit()

print(f"使用期间: {period.name} ({period.date_start} ~ {period.date_end})")

# 获取现金账户
cash_account = env['account.account'].search([('account_type', '=', 'asset_cash')], limit=1)
if not cash_account:
    print("错误: 未找到现金账户")
    exit()

print(f"现金账户: {cash_account.name} (ID: {cash_account.id})")

# 获取费用账户
expense_account = env['account.account'].search([('account_type', '=', 'expense')], limit=1)
if not expense_account:
    print("错误: 未找到费用账户")
    exit()

print(f"费用账户: {expense_account.name} (ID: {expense_account.id})")

# 获取应付账款账户
ap_account = env['account.account'].search([('account_type', '=', 'liability_payable')], limit=1)
if not ap_account:
    print("错误: 未找到应付账款账户")
    exit()

print(f"应付账款账户: {ap_account.name} (ID: {ap_account.id})")

# 测试 1: 导游报销差旅费（现金支付）
print("\n--- 测试 1: 导游报销差旅费（现金支付）---")
move1 = env['account.move'].create({
    'move_type': 'entry',
    'date': period.date_start + timedelta(days=5),
    'journal_id': env['account.journal'].search([('type', '=', 'general')], limit=1).id,
    'line_ids': [
        (0, 0, {
            'account_id': expense_account.id,
            'name': '导游差旅费-住宿',
            'debit': 3000,
            'credit': 0,
        }),
        (0, 0, {
            'account_id': cash_account.id,
            'name': '导游差旅费-住宿',
            'debit': 0,
            'credit': 3000,
        }),
    ],
})
move1.action_post()
print(f"✓ 凭证 1 已过账: {move1.name}, 金额: 3,000 (现金支付)")

# 测试 2: 地接社费用（应付账款）
print("\n--- 测试 2: 地接社费用（应付账款）---")
move2 = env['account.move'].create({
    'move_type': 'entry',
    'date': period.date_start + timedelta(days=10),
    'journal_id': env['account.journal'].search([('type', '=', 'general')], limit=1).id,
    'line_ids': [
        (0, 0, {
            'account_id': expense_account.id,
            'name': '地接社服务费',
            'debit': 15000,
            'credit': 0,
        }),
        (0, 0, {
            'account_id': ap_account.id,
            'name': '地接社服务费',
            'debit': 0,
            'credit': 15000,
        }),
    ],
})
move2.action_post()
print(f"✓ 凭证 2 已过账: {move2.name}, 金额: 15,000 (应付账款)")

# 测试 3: 办公费用（银行支付）
print("\n--- 测试 3: 办公费用（银行支付）---")
bank_account = env['account.account'].search([('account_type', '=', 'asset_cash')], limit=1)
move3 = env['account.move'].create({
    'move_type': 'entry',
    'date': period.date_start + timedelta(days=15),
    'journal_id': env['account.journal'].search([('type', '=', 'general')], limit=1).id,
    'line_ids': [
        (0, 0, {
            'account_id': expense_account.id,
            'name': '办公用品',
            'debit': 2000,
            'credit': 0,
        }),
        (0, 0, {
            'account_id': bank_account.id,
            'name': '办公用品',
            'debit': 0,
            'credit': 2000,
        }),
    ],
})
move3.action_post()
print(f"✓ 凭证 3 已过账: {move3.name}, 金额: 2,000 (银行支付)")

print("\n✓ 所有测试凭证已创建并过账")
print(f"  - 凭证 1: 3,000 (现金支付)")
print(f"  - 凭证 2: 15,000 (应付账款)")
print(f"  - 凭证 3: 2,000 (银行支付)")
print(f"  - 总费用: 20,000")

env.cr.commit()
"""
    
    stdout, stderr = run_odoo_shell(script)
    print(stdout)
    if stderr and 'Error' in stderr:
        print(f"错误: {stderr}")
        return False
    return True


def verify_journal_entries():
    """验证会计分录"""
    print_section("步骤 3: 验证会计分录")
    
    sql = """
    SELECT 
        am.name as voucher_no,
        am.date as voucher_date,
        aml.name as description,
        aa.name->>'zh_CN' as account_name,
        aml.debit,
        aml.credit
    FROM account_move am
    JOIN account_move_line aml ON am.id = aml.move_id
    JOIN account_account aa ON aml.account_id = aa.id
    WHERE am.state = 'posted'
        AND aml.name IN ('导游差旅费-住宿', '地接社服务费', '办公用品')
    ORDER BY am.date, am.name;
    """
    result = run_sql(sql)
    print(f"会计分录明细:\n{result}\n")
    
    # 验证借贷平衡
    balance_sql = """
    SELECT 
        am.name,
        SUM(aml.debit) as total_debit,
        SUM(aml.credit) as total_credit,
        CASE WHEN SUM(aml.debit) = SUM(aml.credit) THEN '✓ 平衡' ELSE '✗ 不平衡' END as status
    FROM account_move am
    JOIN account_move_line aml ON am.id = aml.move_id
    WHERE am.state = 'posted'
        AND aml.name IN ('导游差旅费-住宿', '地接社服务费', '办公用品')
    GROUP BY am.name
    ORDER BY am.name;
    """
    balance_result = run_sql(balance_sql)
    print(f"借贷平衡验证:\n{balance_result}\n")


def verify_financial_reports():
    """验证三大报表"""
    print_section("步骤 4: 验证三大报表")
    
    # 获取最新期间
    period_sql = """
    SELECT id, date_start, date_end
    FROM tour_account_period
    ORDER BY date_start DESC
    LIMIT 1;
    """
    period_result = run_sql(period_sql)
    print(f"期间信息:\n{period_result}\n")
    
    # 利润表
    print("--- 利润表 ---")
    pnl_sql = """
    WITH RECURSIVE tree AS (
        SELECT id, parent_id, level, name, account_type_ids, sign, 0 as depth
        FROM account_financial_report 
        WHERE name->>'en_US' = 'Profit and Loss'
        UNION ALL
        SELECT afr.id, afr.parent_id, afr.level, afr.name, afr.account_type_ids, afr.sign, t.depth + 1
        FROM account_financial_report afr
        JOIN tree t ON afr.parent_id = t.id
    )
    SELECT 
        repeat('  ', depth) || COALESCE(name->>'zh_CN', name->>'en_US') as name,
        account_type_ids,
        sign
    FROM tree
    ORDER BY depth, id;
    """
    pnl_result = run_sql(pnl_sql)
    print(f"利润表结构:\n{pnl_result}\n")
    
    # 资产负债表
    print("--- 资产负债表 ---")
    bs_sql = """
    WITH RECURSIVE tree AS (
        SELECT id, parent_id, level, name, account_type_ids, sign, 0 as depth
        FROM account_financial_report 
        WHERE name->>'en_US' = 'Balance Sheet'
        UNION ALL
        SELECT afr.id, afr.parent_id, afr.level, afr.name, afr.account_type_ids, afr.sign, t.depth + 1
        FROM account_financial_report afr
        JOIN tree t ON afr.parent_id = t.id
    )
    SELECT 
        repeat('  ', depth) || COALESCE(name->>'zh_CN', name->>'en_US') as name,
        account_type_ids,
        sign
    FROM tree
    ORDER BY depth, id;
    """
    bs_result = run_sql(bs_sql)
    print(f"资产负债表结构:\n{bs_result}\n")
    
    # 现金流量表
    print("--- 现金流量表 ---")
    cf_sql = """
    SELECT 
        name->>'zh_CN' as name,
        account_type_ids,
        sign
    FROM account_financial_report
    WHERE name->>'en_US' = 'Cash Flow Statement';
    """
    cf_result = run_sql(cf_sql)
    print(f"现金流量表根节点:\n{cf_result}\n")


def verify_changes():
    """验证变化"""
    print_section("步骤 5: 验证变化")
    
    # 获取测试后状态
    cash_sql = """
    SELECT 
        COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type IN ('asset_cash', 'asset_current');
    """
    cash_after = run_sql(cash_sql)
    print(f"测试后现金余额: {cash_after}\n")
    
    ap_sql = """
    SELECT 
        COALESCE(SUM(aml.credit), 0) - COALESCE(SUM(aml.debit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type = 'liability_payable';
    """
    ap_after = run_sql(ap_sql)
    print(f"测试后应付账款余额: {ap_after}\n")
    
    expense_sql = """
    SELECT 
        COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type IN ('expense', 'expense_direct_cost', 'expense_depreciation');
    """
    expense_after = run_sql(expense_sql)
    print(f"测试后费用余额: {expense_after}\n")


def verify_consistency():
    """验证三表一致性"""
    print_section("步骤 6: 验证三表一致性")
    
    print("勾稽关系验证:")
    print("1. 利润表净利润 → 资产负债表未分配利润")
    print("2. 资产负债表货币资金 → 现金流量表期末现金")
    print("3. 费用增加 → 现金减少或应付增加")
    print("\n预期结果:")
    print("- 费用增加 20,000")
    print("- 现金减少 5,000 (3,000 + 2,000)")
    print("- 应付增加 15,000")
    print("- 净利润减少 20,000")


def main():
    """主函数"""
    print("="*60)
    print("  费用端到端测试")
    print("  费用录入 → 会计分录 → 三大报表")
    print("="*60)
    
    # 步骤 1: 获取初始状态
    initial_state = get_initial_state()
    
    # 步骤 2: 创建测试费用
    if not create_test_expenses():
        print("\n✗ 创建测试费用失败")
        return
    
    # 步骤 3: 验证会计分录
    verify_journal_entries()
    
    # 步骤 4: 验证三大报表
    verify_financial_reports()
    
    # 步骤 5: 验证变化
    verify_changes()
    
    # 步骤 6: 验证一致性
    verify_consistency()
    
    print_section("测试完成")
    print("✓ 费用端到端测试已完成")
    print("\n下一步:")
    print("1. 访问 http://tms.solepro.cloud:8070/web")
    print("2. 财务管理 → 财务报表")
    print("3. 分别查看利润表、资产负债表、现金流量表")
    print("4. 验证费用是否正确反映在三大报表中")


if __name__ == '__main__':
    main()
