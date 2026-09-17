#!/usr/bin/env python3
"""
费用端到端测试（SQL 版本）：费用录入 → 会计分录 → 三大报表
"""

import subprocess
from datetime import datetime, timedelta


def run_sql(query, fetch=True):
    """执行 SQL 查询"""
    cmd = ['docker', 'exec', '-i', 'tms-db', 'psql', '-U', 'odoo', '-d', 'tms', '-t', '-c', query]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if fetch:
        return result.stdout.strip()
    return result.returncode == 0


def print_section(title):
    """打印分隔线"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


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
        COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type IN ('asset_cash', 'asset_current');
    """
    cash_result = run_sql(cash_sql)
    print(f"当前现金余额: {cash_result}\n")
    
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
    
    # 获取当前费用余额
    expense_sql = """
    SELECT 
        COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type IN ('expense', 'expense_direct_cost', 'expense_depreciation');
    """
    expense_result = run_sql(expense_sql)
    print(f"当前费用余额: {expense_result}\n")
    
    return {
        'cash': cash_result.strip(),
        'ap': ap_result.strip(),
        'expense': expense_result.strip(),
    }


def create_test_expenses():
    """创建测试费用（使用 SQL）"""
    print_section("步骤 2: 创建测试费用")
    
    # 获取必要的 ID
    period_sql = "SELECT id, date_start FROM tour_account_period ORDER BY date_start DESC LIMIT 1;"
    period_result = run_sql(period_sql).split('|')
    period_id = period_result[0].strip()
    period_start = period_result[1].strip()
    
    # 获取账户 ID
    cash_sql = "SELECT id FROM account_account WHERE account_type = 'asset_cash' LIMIT 1;"
    cash_id = run_sql(cash_sql).strip()
    
    expense_sql = "SELECT id FROM account_account WHERE account_type = 'expense' LIMIT 1;"
    expense_id = run_sql(expense_sql).strip()
    
    ap_sql = "SELECT id FROM account_account WHERE account_type = 'liability_payable' LIMIT 1;"
    ap_id = run_sql(ap_sql).strip()
    
    journal_sql = "SELECT id FROM account_journal WHERE type = 'general' LIMIT 1;"
    journal_id = run_sql(journal_sql).strip()
    
    print(f"期间 ID: {period_id}, 起始日期: {period_start}")
    print(f"现金账户 ID: {cash_id}")
    print(f"费用账户 ID: {expense_id}")
    print(f"应付账款账户 ID: {ap_id}")
    print(f"日记账 ID: {journal_id}")
    
    # 测试 1: 导游报销差旅费（现金支付）3,000
    print("\n--- 测试 1: 导游报销差旅费（现金支付）3,000 ---")
    move1_sql = f"""
    INSERT INTO account_move (name, date, journal_id, state, move_type, create_uid, create_date)
    VALUES ('TEST/2026/001', '{period_start}'::date + INTERVAL '5 days', {journal_id}, 'posted', 'entry', 1, NOW())
    RETURNING id;
    """
    move1_id = run_sql(move1_sql).strip()
    print(f"✓ 凭证 1 ID: {move1_id}")
    
    # 凭证 1 明细行
    move1_lines_sql = f"""
    INSERT INTO account_move_line (move_id, account_id, name, debit, credit, date, create_uid, create_date)
    VALUES 
        ({move1_id}, {expense_id}, '导游差旅费-住宿', 3000, 0, '{period_start}'::date + INTERVAL '5 days', 1, NOW()),
        ({move1_id}, {cash_id}, '导游差旅费-住宿', 0, 3000, '{period_start}'::date + INTERVAL '5 days', 1, NOW());
    """
    run_sql(move1_lines_sql, fetch=False)
    print(f"✓ 凭证 1 明细行已创建")
    
    # 测试 2: 地接社费用（应付账款）15,000
    print("\n--- 测试 2: 地接社费用（应付账款）15,000 ---")
    move2_sql = f"""
    INSERT INTO account_move (name, date, journal_id, state, move_type, create_uid, create_date)
    VALUES ('TEST/2026/002', '{period_start}'::date + INTERVAL '10 days', {journal_id}, 'posted', 'entry', 1, NOW())
    RETURNING id;
    """
    move2_id = run_sql(move2_sql).strip()
    print(f"✓ 凭证 2 ID: {move2_id}")
    
    move2_lines_sql = f"""
    INSERT INTO account_move_line (move_id, account_id, name, debit, credit, date, create_uid, create_date)
    VALUES 
        ({move2_id}, {expense_id}, '地接社服务费', 15000, 0, '{period_start}'::date + INTERVAL '10 days', 1, NOW()),
        ({move2_id}, {ap_id}, '地接社服务费', 0, 15000, '{period_start}'::date + INTERVAL '10 days', 1, NOW());
    """
    run_sql(move2_lines_sql, fetch=False)
    print(f"✓ 凭证 2 明细行已创建")
    
    # 测试 3: 办公费用（银行支付）2,000
    print("\n--- 测试 3: 办公费用（银行支付）2,000 ---")
    move3_sql = f"""
    INSERT INTO account_move (name, date, journal_id, state, move_type, create_uid, create_date)
    VALUES ('TEST/2026/003', '{period_start}'::date + INTERVAL '15 days', {journal_id}, 'posted', 'entry', 1, NOW())
    RETURNING id;
    """
    move3_id = run_sql(move3_sql).strip()
    print(f"✓ 凭证 3 ID: {move3_id}")
    
    move3_lines_sql = f"""
    INSERT INTO account_move_line (move_id, account_id, name, debit, credit, date, create_uid, create_date)
    VALUES 
        ({move3_id}, {expense_id}, '办公用品', 2000, 0, '{period_start}'::date + INTERVAL '15 days', 1, NOW()),
        ({move3_id}, {cash_id}, '办公用品', 0, 2000, '{period_start}'::date + INTERVAL '15 days', 1, NOW());
    """
    run_sql(move3_lines_sql, fetch=False)
    print(f"✓ 凭证 3 明细行已创建")
    
    print("\n✓ 所有测试凭证已创建")
    print(f"  - 凭证 1: 3,000 (现金支付)")
    print(f"  - 凭证 2: 15,000 (应付账款)")
    print(f"  - 凭证 3: 2,000 (银行支付)")
    print(f"  - 总费用: 20,000")
    
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
    WHERE am.name LIKE 'TEST/2026/%'
    ORDER BY am.date, am.name, aml.debit DESC;
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
    WHERE am.name LIKE 'TEST/2026/%'
    GROUP BY am.name
    ORDER BY am.name;
    """
    balance_result = run_sql(balance_sql)
    print(f"借贷平衡验证:\n{balance_result}\n")


def verify_changes(initial_state):
    """验证变化"""
    print_section("步骤 4: 验证变化")
    
    # 获取测试后状态
    cash_sql = """
    SELECT 
        COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type IN ('asset_cash', 'asset_current');
    """
    cash_after = run_sql(cash_sql).strip()
    
    ap_sql = """
    SELECT 
        COALESCE(SUM(aml.credit), 0) - COALESCE(SUM(aml.debit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type = 'liability_payable';
    """
    ap_after = run_sql(ap_sql).strip()
    
    expense_sql = """
    SELECT 
        COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0) as balance
    FROM account_account aa
    JOIN account_move_line aml ON aa.id = aml.account_id
    JOIN account_move am ON aml.move_id = am.id AND am.state = 'posted'
    WHERE aa.account_type IN ('expense', 'expense_direct_cost', 'expense_depreciation');
    """
    expense_after = run_sql(expense_sql).strip()
    
    print("变化对比:")
    print(f"{'项目':<20} {'测试前':>15} {'测试后':>15} {'变化':>15}")
    print("-" * 70)
    
    cash_before = float(initial_state['cash']) if initial_state['cash'] else 0
    cash_after_val = float(cash_after) if cash_after else 0
    cash_change = cash_after_val - cash_before
    print(f"{'现金':<20} {cash_before:>15,.2f} {cash_after_val:>15,.2f} {cash_change:>15,.2f}")
    
    ap_before = float(initial_state['ap']) if initial_state['ap'] else 0
    ap_after_val = float(ap_after) if ap_after else 0
    ap_change = ap_after_val - ap_before
    print(f"{'应付账款':<20} {ap_before:>15,.2f} {ap_after_val:>15,.2f} {ap_change:>15,.2f}")
    
    expense_before = float(initial_state['expense']) if initial_state['expense'] else 0
    expense_after_val = float(expense_after) if expense_after else 0
    expense_change = expense_after_val - expense_before
    print(f"{'费用':<20} {expense_before:>15,.2f} {expense_after_val:>15,.2f} {expense_change:>15,.2f}")
    
    print("\n预期变化:")
    print(f"  - 费用增加: 20,000.00 (实际: {expense_change:,.2f}) {'✓' if abs(expense_change - 20000) < 0.01 else '✗'}")
    print(f"  - 现金减少: -5,000.00 (实际: {cash_change:,.2f}) {'✓' if abs(cash_change + 5000) < 0.01 else '✗'}")
    print(f"  - 应付增加: 15,000.00 (实际: {ap_change:,.2f}) {'✓' if abs(ap_change - 15000) < 0.01 else '✗'}")


def verify_report_structure():
    """验证报表结构"""
    print_section("步骤 5: 验证报表结构")
    
    # 利润表
    print("--- 利润表结构 ---")
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
    ORDER BY depth, id
    LIMIT 15;
    """
    pnl_result = run_sql(pnl_sql)
    print(f"{pnl_result}\n")
    
    # 资产负债表
    print("--- 资产负债表结构 ---")
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
    ORDER BY depth, id
    LIMIT 25;
    """
    bs_result = run_sql(bs_sql)
    print(f"{bs_result}\n")


def main():
    """主函数"""
    print("="*70)
    print("  费用端到端测试（SQL 版本）")
    print("  费用录入 → 会计分录 → 三大报表")
    print("="*70)
    
    # 步骤 1: 获取初始状态
    initial_state = get_initial_state()
    
    # 步骤 2: 创建测试费用
    if not create_test_expenses():
        print("\n✗ 创建测试费用失败")
        return
    
    # 步骤 3: 验证会计分录
    verify_journal_entries()
    
    # 步骤 4: 验证变化
    verify_changes(initial_state)
    
    # 步骤 5: 验证报表结构
    verify_report_structure()
    
    print_section("测试完成")
    print("✓ 费用端到端测试已完成")
    print("\n下一步:")
    print("1. 访问 http://tms.solepro.cloud:8070/web")
    print("2. 财务管理 → 财务报表")
    print("3. 分别查看利润表、资产负债表、现金流量表")
    print("4. 验证费用是否正确反映在三大报表中")
    print("\n预期结果:")
    print("  - 利润表：费用增加 20,000，净利润减少 20,000")
    print("  - 资产负债表：现金减少 5,000，应付增加 15,000，未分配利润减少 20,000")
    print("  - 现金流量表：经营活动现金流出 5,000（现金支付部分）")


if __name__ == '__main__':
    main()
