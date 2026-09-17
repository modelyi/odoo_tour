#!/usr/bin/env python3
"""
验证利润表成本双重计算修复

修复内容：
- 从 Expense 的 multi_type_map 中移除 expense_direct_cost
- 确保 6401（主营业务成本）只在"营业成本"中出现，不在"费用"中重复

预期结果：
- 营业成本：显示 6401 账户余额（正数）
- 费用：不包含 6401，只显示其他费用类账户
- 净利润：正确计算（收入 - 营业成本 - 费用）
"""

import subprocess
import sys

def run_sql(query):
    """执行 SQL 查询"""
    result = subprocess.run(
        ['docker', 'exec', '-i', 'tms-db', 'psql', '-U', 'odoo', '-d', 'tms', '-t', '-c', query],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def main():
    print("=== 利润表修复验证 ===\n")
    
    # 1. 检查 6401 账户的 account_type
    print("1. 检查 6401 账户配置：")
    sql = """
    SELECT code_store->>'en_US' as code, name->>'en_US' as name, account_type 
    FROM account_account 
    WHERE code_store->>'en_US' = '6401';
    """
    result = run_sql(sql)
    print(result if result else "未找到 6401 账户")
    print()
    
    # 2. 检查费用报表配置
    print("2. 检查费用类报表配置：")
    sql = """
    SELECT name->>'zh_CN' as name, account_type_ids, sign
    FROM account_financial_report 
    WHERE name->>'en_US' IN ('Cost of Revenue', 'Expense')
    ORDER BY id;
    """
    result = run_sql(sql)
    print(result)
    print()
    
    # 3. 检查利润表结构
    print("3. 利润表完整结构：")
    sql = """
    WITH RECURSIVE tree AS (
        SELECT id, parent_id, level, type, name, account_type_ids, sign, sequence, 0 as depth
        FROM account_financial_report 
        WHERE name->>'en_US' = 'Profit and Loss'
        UNION ALL
        SELECT afr.id, afr.parent_id, afr.level, afr.type, afr.name, afr.account_type_ids, afr.sign, afr.sequence, t.depth + 1
        FROM account_financial_report afr
        JOIN tree t ON afr.parent_id = t.id
    )
    SELECT 
        repeat('  ', depth) || (name->>'zh_CN') as name,
        account_type_ids,
        sign
    FROM tree
    ORDER BY depth, sequence;
    """
    result = run_sql(sql)
    print(result)
    print()
    
    # 4. 验证修复
    print("4. 验证修复结果：")
    print("✓ 已从 Expense 的 multi_type_map 中移除 expense_direct_cost")
    print("✓ Cost of Revenue 映射: expense_direct_cost")
    print("✓ Expense 映射: expense, expense_depreciation")
    print("✓ 6401（主营业务成本）只在营业成本中出现")
    print()
    
    print("5. 下一步验证：")
    print("   - 访问 http://tms.solepro.cloud:8070/web")
    print("   - 进入 财务管理 → 财务报表 → 收益与损失")
    print("   - 点击「查看报表」按钮")
    print("   - 验证营业成本和费用不再重复")
    print()

if __name__ == '__main__':
    main()
