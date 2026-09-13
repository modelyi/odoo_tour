# -*- coding: utf-8 -*-
"""BS-14 冒烟测试：仅处理前 N 个团，验证凭证构建与借贷平衡。"""
import datetime
from collections import defaultdict

GROSS = ('1', '12', '13', '14', '15')
VAT_RATE = 6.0


def _acc(code):
    return env['account.account'].search([('code', '=', code)], limit=1)


acc_gross = _acc('6001.01')
acc_dt = _acc('6001.02')
acc_prepay = _acc('2203.01')
acc_receivable = _acc('1122.01')
acc_tax = _acc('2221.01')
acc_cost = _acc('6401')
acc_dd = _acc('2241.01')
journal = env['account.journal'].search([('type', '=', 'general')], limit=1) or \
    env['account.journal'].search([], limit=1)
print('accounts ok: gross=%s dt=%s prepay=%s recv=%s tax=%s cost=%s dd=%s' % (
    acc_gross.code, acc_dt.code, acc_prepay.code, acc_receivable.code,
    acc_tax.code, acc_cost.code, acc_dd.code))
print('journal=%s' % journal.name)

# 收入侧冒烟：取 3 个有 income_move_id 的团
sample = env['tour.plan'].search(
    [('biz_mode', 'in', GROSS), ('income_move_id', '!=', False)], limit=3)
print('sample plans: %s' % [p.plan_code for p in sample])

for p in sample:
    old_move = p.income_move_id
    old_net = old_tax = 0.0
    for ln in old_move.line_ids:
        if ln.account_id.id == acc_dt.id:
            old_net += ln.credit - ln.debit
        elif ln.account_id.id == acc_tax.id:
            old_tax += ln.credit - ln.debit
    old_total = round(old_net + old_tax, 2)
    new_total = round(float(p.in_com_quo_sum or 0.0), 2)
    new_net = round(new_total / (1 + VAT_RATE / 100.0), 2)
    new_tax = round(new_total - new_net, 2)
    to_prepay = round(min(max(p.sum_pay_normal or 0.0, 0.0), new_total), 2)
    to_receivable = round(new_total - to_prepay, 2)
    p._ensure_analytic_account()
    ana = {str(p.analytic_account_id.id): 100.0}
    partner = p.supplier_id.id if p.supplier_id else False

    lines = []
    if old_net > 0:
        lines.append(('acc_dt', 'D', round(old_net, 2)))
    if old_tax > 0:
        lines.append(('acc_tax', 'D', round(old_tax, 2)))
    if old_total > 0:
        lines.append(('acc_prepay', 'C', old_total))
    if to_prepay > 0:
        lines.append(('acc_prepay', 'D', to_prepay))
    if to_receivable > 0:
        lines.append(('acc_receivable', 'D', to_receivable))
    if new_net > 0:
        lines.append(('acc_gross', 'C', new_net))
    if new_tax > 0:
        lines.append(('acc_tax', 'C', new_tax))

    deb = sum(a for _, d, a in lines if d == 'D')
    cre = sum(a for _, d, a in lines if d == 'C')
    print('plan %s: old_net=%.2f old_tax=%.2f old_total=%.2f new_total=%.2f '
          'new_net=%.2f new_tax=%.2f to_prepay=%.2f to_recv=%.2f | deb=%.2f cre=%.2f diff=%.2f' % (
              p.plan_code, old_net, old_tax, old_total, new_total, new_net,
              new_tax, to_prepay, to_receivable, deb, cre, round(deb - cre, 2)))

print('=== 成本侧冒烟：取 2 个 41 团 ===')
cost_by_analytic = defaultdict(float)
for ln in env['account.move.line'].search([
        ('account_id', '=', acc_cost.id), ('parent_state', '=', 'posted')]):
    amt = ln.debit - ln.credit
    for al in ln.analytic_line_ids:
        cost_by_analytic[al.account_id.id] += amt
sample41 = env['tour.plan'].search([('biz_mode', '=', '41')], limit=2)
for p in sample41:
    p._ensure_analytic_account()
    aa = p.analytic_account_id
    amt = round(cost_by_analytic.get(aa.id, 0.0), 2)
    print('plan %s: 6401 cost = %.2f' % (p.plan_code, amt))
