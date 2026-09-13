# -*- coding: utf-8 -*-
"""BS-14 诊断：当前科目余额 / biz_mode 分布 / 纳税人配置。"""
from collections import defaultdict


def bal(code):
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        print('MISSING ACCOUNT', code)
        return None
    lines = env['account.move.line'].search([
        ('account_id', '=', acc.id), ('parent_state', '=', 'posted')])
    d = sum(lines.mapped('debit'))
    c = sum(lines.mapped('credit'))
    print('%-10s id=%-5s debit=%15.2f credit=%15.2f net(debit-credit)=%15.2f' %
          (code, acc.id, d, c, d - c))
    return d - c


print('=== 公司纳税人配置 ===')
co = env.company
for f in ('tour_taxpayer_type', 'tour_vat_rate', 'tour_vat_levy_rate',
          'tour_diff_tax_enabled'):
    try:
        print('  %s = %r' % (f, co[f]))
    except Exception as e:
        print('  %s = <err %s>' % (f, e))

print('=== 关键科目余额（已过账） ===')
for code in ('6001.01', '6001.02', '6001.03', '6401', '2241.01', '2203.01', '2221.01'):
    bal(code)

print('=== biz_mode 分布（tour.plan 总数 %d）===' % env['tour.plan'].search_count([]))
rows = env['tour.plan'].read_group(
    [('biz_mode', '!=', False)],
    ['biz_mode'], ['biz_mode'], lazy=False)
bm = {r['biz_mode']: r['__count'] for r in rows}
for k in sorted(bm, key=lambda x: str(x)):
    print('  biz_mode=%-4s count=%d' % (k, bm[k]))

print('=== 收入凭证 income_move_id 已确认数 ===')
print('  plans with income_move_id=%d' %
      env['tour.plan'].search_count([('income_move_id', '!=', False)]))

print('=== income_move_id 按 biz_mode ===')
rows = env['tour.plan'].read_group(
    [('income_move_id', '!=', False), ('biz_mode', '!=', False)],
    ['biz_mode'], ['biz_mode'], lazy=False)
for r in rows:
    print('  biz_mode=%-4s income_move=%d' % (r['biz_mode'], r['__count']))

print('=== 6001.02 已过账行按 biz_mode 归集（via analytic 反查团）===')
acc_dt = env['account.account'].search([('code', '=', '6001.02')], limit=1)
if acc_dt:
    lines = env['account.move.line'].search([
        ('account_id', '=', acc_dt.id), ('parent_state', '=', 'posted')])
    by_bm = defaultdict(float)
    for ln in lines:
        # 通过 analytic_line 反查 tour.plan
        plan = ln.analytic_line_ids.analytic_account_id.tour_plan_id
        bm_key = plan.biz_mode if plan else '(无团)'
        by_bm[bm_key] += ln.credit - ln.debit  # 收入贷方为正
    for k in sorted(by_bm, key=lambda x: str(x)):
        print('  biz_mode=%-4s 6001.02贷方净额=%15.2f' % (k, by_bm[k]))

print('=== 6401 中 biz_mode=41 成本（via analytic） ===')
acc_cost = env['account.account'].search([('code', '=', '6401')], limit=1)
if acc_cost:
    lines = env['account.move.line'].search([
        ('account_id', '=', acc_cost.id), ('parent_state', '=', 'posted')])
    dd_cost = 0.0
    for ln in lines:
        plan = ln.analytic_line_ids.analytic_account_id.tour_plan_id
        if plan and plan.biz_mode == '41':
            dd_cost += ln.debit - ln.credit
    print('  6401 中 41 团净借方=%15.2f' % dd_cost)

print('=== 已过账 account.move 总数 / move.line 总数 ===')
print('  moves=%d lines=%d' % (
    env['account.move'].search_count([('state', '=', 'posted')]),
    env['account.move.line'].search_count([('parent_state', '=', 'posted')])))
