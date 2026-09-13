# -*- coding: utf-8 -*-
"""BS-14 精确拆分：prepay/invoice 流团的金额口径，判断补记 counterpart。"""
GROSS = ('1', '12', '13', '14', '15')


def agg(domain, field):
    rows = env['tour.plan'].read_group(domain, [field], [], lazy=False)
    return rows[0][field] if rows and rows[0][field] is not None else 0.0


# prepay 流：income_move_id 已设置
pre = [('biz_mode', 'in', GROSS), ('income_move_id', '!=', False)]
print('=== PREPAY 流（income_move_id）GROSS 团 ===')
print('  count           = %d' % env['tour.plan'].search_count(pre))
print('  in_com_quo_sum  = %15.2f' % agg(pre, 'in_com_quo_sum'))
print('  in_sum          = %15.2f' % agg(pre, 'in_sum'))
print('  out_sum         = %15.2f' % agg(pre, 'out_sum'))
print('  in_sum-out_sum  = %15.2f' % (agg(pre, 'in_sum') - agg(pre, 'out_sum')))
print('  sum_pay_normal  = %15.2f' % agg(pre, 'sum_pay_normal'))
print('  sum_un_pay      = %15.2f' % agg(pre, 'sum_un_pay'))

# invoice 流：有 out_invoice（move.tour_plan_id），无 income_move_id
inv_plan_ids = env['account.move'].search(
    [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
     ('tour_plan_id', '!=', False)]).mapped('tour_plan_id').ids
inv = [('id', 'in', inv_plan_ids), ('income_move_id', '=', False)]
print('=== INVOICE 流（out_invoice, 无 income_move_id）GROSS 团 ===')
print('  count           = %d' % env['tour.plan'].search_count(inv))
print('  in_com_quo_sum  = %15.2f' % agg(inv, 'in_com_quo_sum'))
print('  in_sum          = %15.2f' % agg(inv, 'in_sum'))
print('  out_sum         = %15.2f' % agg(inv, 'out_sum'))
print('  in_sum-out_sum  = %15.2f' % (agg(inv, 'in_sum') - agg(inv, 'out_sum')))
print('  sum_pay_normal  = %15.2f' % agg(inv, 'sum_pay_normal'))
print('  sum_un_pay      = %15.2f' % agg(inv, 'sum_un_pay'))

# 无收入 GROSS 团
no_rev = [('biz_mode', 'in', GROSS), ('income_move_id', '=', False),
          ('id', 'not in', inv_plan_ids)]
print('=== 无收入 GROSS 团（既无 income_move 也无 out_invoice）===')
print('  count           = %d' % env['tour.plan'].search_count(no_rev))
print('  in_com_quo_sum  = %15.2f' % agg(no_rev, 'in_com_quo_sum'))
print('  sum_pay_normal  = %15.2f' % agg(no_rev, 'sum_pay_normal'))
print('  sum_un_pay      = %15.2f' % agg(no_rev, 'sum_un_pay'))

# 41 团成本口径（用于 2241.01 转出金额）
print('=== 41 团 6401 已过账成本精确汇总 ===')
acc_cost = env['account.account'].search([('code', '=', '6401')], limit=1)
dd_plans = env['tour.plan'].search([('biz_mode', '=', '41')])
tot = 0.0
n = 0
for p in dd_plans:
    aa = p.analytic_account_id
    if not aa:
        continue
    lines = env['account.move.line'].search([
        ('account_id', '=', acc_cost.id), ('parent_state', '=', 'posted'),
        ('analytic_line_ids.account_id', '=', aa.id)])
    amt = sum(l.debit - l.credit for l in lines)
    if amt != 0.0:
        tot += amt
        n += 1
print('  41 团有 6401 成本: %d 团, 合计净借 = %15.2f' % (n, tot))
