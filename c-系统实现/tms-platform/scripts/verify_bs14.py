# -*- coding: utf-8 -*-
"""BS-14 验收：修正后科目余额 / 毛利 / 全局借贷平衡。"""


def bal(code):
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        print('MISSING %s' % code)
        return 0.0
    lines = env['account.move.line'].search([
        ('account_id', '=', acc.id), ('parent_state', '=', 'posted')])
    d = sum(lines.mapped('debit'))
    c = sum(lines.mapped('credit'))
    print('%-10s debit=%16.2f credit=%16.2f net(debit-credit)=%16.2f' %
          (code, d, c, d - c))
    return d - c


print('=== 修正后科目余额（已过账） ===')
r_gross = bal('6001.01')
r_dt = bal('6001.02')
r_dd = bal('6001.03')
c_cost = bal('6401')
dd_payable = bal('2241.01')
bal('2221.01')

print('=== 毛利（含税口径：收入全额 vs 成本） ===')
# 收入含税 = 6001.01 净额*1.06 + 6001.03 净额*1.06（近似，按 6% 还原）
gross_tax_incl = -r_gross * 1.06  # 贷方为负，还原含税
dd_tax_incl = -r_dd * 1.06
rev_incl = gross_tax_incl + dd_tax_incl
print('  6001.01 含税 ≈ %16.2f' % gross_tax_incl)
print('  6001.03 含税 ≈ %16.2f' % dd_tax_incl)
print('  收入合计含税 ≈ %16.2f' % rev_incl)
print('  成本 6401 = %16.2f' % c_cost)
print('  毛利(含税口径) = %16.2f' % (rev_incl - c_cost))

print('=== 全局借贷平衡 ===')
env.cr.execute("""
    SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0)
    FROM account_move_line WHERE parent_state = 'posted'
""")
d, c = env.cr.fetchone()
print('  total debit=%.2f  total credit=%.2f  diff=%.2f' % (d, c, d - c))

print('=== 冲销重记统计 ===')
print('  BS14-RC 收入修正凭证 = %d' %
      env['account.move'].search_count([('ref', '=like', 'BS14-RC-%')]))
print('  BS14-CC 成本转出凭证 = %d' %
      env['account.move'].search_count([('ref', '=like', 'BS14-CC-%')]))
