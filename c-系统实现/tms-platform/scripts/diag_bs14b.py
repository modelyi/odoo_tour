# -*- coding: utf-8 -*-
"""BS-14 深度诊断：按流（prepay/invoice）拆分、41 成本、金额口径。"""
from collections import defaultdict

GROSS = ('1', '12', '13', '14', '15')
DD = ('41',)


def agg(domain, field):
    rows = env['tour.plan'].read_group(domain, [field], [], lazy=False)
    return rows[0][field] if rows and rows[0][field] is not None else 0.0


print('=== tour.plan 金额口径（GROSS 模式 1/12/13/14/15）===')
gd = [('biz_mode', 'in', GROSS)]
print('  in_com_quo_sum = %15.2f' % agg(gd, 'in_com_quo_sum'))
print('  in_sum         = %15.2f' % agg(gd, 'in_sum'))
print('  out_sum        = %15.2f' % agg(gd, 'out_sum'))
print('  sum_pay_normal = %15.2f' % agg(gd, 'sum_pay_normal'))
print('  sum_un_pay     = %15.2f' % agg(gd, 'sum_un_pay'))

print('=== GROSS 模式团按流分类 ===')
print('  income_move_id 已确认 = %d' % env['tour.plan'].search_count(
    [('biz_mode', 'in', GROSS), ('income_move_id', '!=', False)]))
print('  invoice_ids 有发票 = %d' % env['tour.plan'].search_count(
    [('biz_mode', 'in', GROSS), ('invoice_ids', '!=', False)]))
print('  两者皆无（未产生收入） = %d' % env['tour.plan'].search_count(
    [('biz_mode', 'in', GROSS), ('income_move_id', '=', False),
     ('invoice_ids', '=', False)]))

print('=== 41 代订模式金额口径 ===')
dd = [('biz_mode', '=', '41')]
print('  in_com_quo_sum = %15.2f' % agg(dd, 'in_com_quo_sum'))
print('  in_sum         = %15.2f' % agg(dd, 'in_sum'))
print('  out_sum        = %15.2f' % agg(dd, 'out_sum'))
print('  in_sum-out_sum = %15.2f' % (agg(dd, 'in_sum') - agg(dd, 'out_sum')))

print('=== 6001.02 已过账行拆分（prepay income_move vs invoice 流）===')
acc_dt = env['account.account'].search([('code', '=', '6001.02')], limit=1)
acc_dd = env['account.account'].search([('code', '=', '6001.03')], limit=1)
acc_gross = env['account.account'].search([('code', '=', '6001.01')], limit=1)


def rev_by_flow(acc):
    lines = env['account.move.line'].search([
        ('account_id', '=', acc.id), ('parent_state', '=', 'posted')])
    prepay = inv = noflow = 0.0
    n_prepay = n_inv = 0
    for ln in lines:
        move = ln.move_id
        plan = ln.analytic_line_ids.account_id.tour_plan_id if ln.analytic_line_ids else False
        credit = ln.credit - ln.debit  # 收入贷方净额
        if move.move_type == 'entry' and plan and plan.income_move_id.id == move.id:
            prepay += credit
            n_prepay += 1
        elif move.move_type in ('out_invoice', 'out_refund'):
            inv += credit
            n_inv += 1
        else:
            noflow += credit
    return prepay, inv, noflow, n_prepay, n_inv


p, i, nf, np_, ni_ = rev_by_flow(acc_dt)
print('  6001.02 prepay流(income_move) 贷净额=%15.2f 行数=%d' % (p, np_))
print('  6001.02 invoice流(out_invoice) 贷净额=%15.2f 行数=%d' % (i, ni_))
print('  6001.02 其它流 贷净额=%15.2f' % nf)
print('  6001.02 合计贷净额=%15.2f' % (p + i + nf))

print('=== 2221.01 销项税 总余额 ===')
acc_tax = env['account.account'].search([('code', '=', '2221.01')], limit=1)
lines = env['account.move.line'].search([
    ('account_id', '=', acc_tax.id), ('parent_state', '=', 'posted')])
print('  2221.01 贷净额 = %15.2f' % sum(l.credit - l.debit for l in lines))

print('=== 6401 中 41 团成本（via analytic）===')
acc_cost = env['account.account'].search([('code', '=', '6401')], limit=1)
lines = env['account.move.line'].search([
    ('account_id', '=', acc_cost.id), ('parent_state', '=', 'posted')])
dd_cost = 0.0
dd_lines = 0
gross_cost = 0.0
other_cost = 0.0
for ln in lines:
    plan = ln.analytic_line_ids.account_id.tour_plan_id if ln.analytic_line_ids else False
    amt = ln.debit - ln.credit
    if plan and plan.biz_mode == '41':
        dd_cost += amt
        dd_lines += 1
    elif plan and plan.biz_mode in GROSS:
        gross_cost += amt
    else:
        other_cost += amt
print('  6401 41团 净借=%15.2f 行数=%d' % (dd_cost, dd_lines))
print('  6401 GROSS团 净借=%15.2f' % gross_cost)
print('  6401 其它(无团/51) 净借=%15.2f' % other_cost)
print('  6401 合计净借=%15.2f' % (dd_cost + gross_cost + other_cost))
