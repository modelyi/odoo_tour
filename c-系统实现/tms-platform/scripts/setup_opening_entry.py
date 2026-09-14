# -*- coding: utf-8 -*-
"""
BS-16 期初建账脚本（幂等，可重复执行）。

在 Odoo shell 中运行（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < scripts/setup_opening_entry.py

动作：
  1. 建/取日记账「期初建账」(type=general, code=OPEN)。
  2. 建/取科目 4001 实收资本 (account_type=equity)。
  3. 建 1 张期初建账凭证（move_type=entry, journal=OPEN, date=2026-01-01,
     ref=期初建账）：借 1002 银行存款 / 贷 4001 实收资本 各 70,954,195.04，action_post。
  4. 验证：银行余额转正、全库借贷 diff=0、资产负债表平衡（资产=负债+权益）、
     利润表不变（6001/6401 净额与建账前一致）。

幂等依据：journal=OPEN 且 ref='期初建账' 的凭证已存在则跳过。
不改动现有经营凭证（仅新增 1 张期初凭证）。
"""
from odoo import fields

OPENING_AMOUNT = 70954195.04
OPENING_DATE = '2026-01-01'
REF = '期初建账'

ASSET_TYPES = ('asset_cash', 'asset_receivable', 'asset_current',
               'asset_non_current', 'asset_fixed', 'asset_prepayments')
LIABILITY_TYPES = ('liability_payable', 'liability_current',
                   'liability_non_current')
EQUITY_TYPES = ('equity', 'equity_unaffected')
INCOME_TYPES = ('income', 'income_other')
EXPENSE_TYPES = ('expense', 'expense_direct_cost', 'expense_depreciation')


def _acc(code):
    a = env['account.account'].search([('code', '=', code)], limit=1)
    return a


def _get_or_create_journal():
    AJ = env['account.journal']
    j = AJ.search([('type', '=', 'general'), ('code', '=', 'OPEN')], limit=1)
    if not j:
        j = AJ.create({
            'name': '期初建账',
            'code': 'OPEN',
            'type': 'general',
            'company_id': env.company.id,
        })
        print('[journal] created OPEN 期初建账 id=%d' % j.id)
    else:
        print('[journal] exists OPEN 期初建账 id=%d' % j.id)
    return j


def _get_or_create_account_4001():
    AA = env['account.account']
    a = AA.search([('code', '=', '4001')], limit=1)
    if not a:
        a = AA.create({
            'code': '4001',
            'name': '实收资本',
            'account_type': 'equity',
            'company_ids': [(6, 0, [env.company.id])],
            'reconcile': False,
        })
        print('[account] created 4001 实收资本 id=%d' % a.id)
    else:
        print('[account] exists 4001 实收资本 id=%d' % a.id)
    return a


def _group_balance():
    """返回 (资产, 负债, 权益, 收入, 费用) 各 account_type 净额，及单科目明细。"""
    AML = env['account.move.line']
    AA = env['account.account']
    agg = AML.read_group([('parent_state', '=', 'posted')],
                         ['debit', 'credit'], ['account_id'])
    acct_by_id = {a.id: a for a in AA.search([])}
    assets = liabilities = equity = income = expense = 0.0
    detail = {}
    for row in agg:
        aid = row['account_id'][0] if row['account_id'] else None
        a = acct_by_id.get(aid)
        if a is None:
            continue
        net = (row['debit'] or 0.0) - (row['credit'] or 0.0)
        t = a.account_type
        if t in ASSET_TYPES:
            assets += net
            detail.setdefault('asset', []).append((a.code, net))
        elif t in LIABILITY_TYPES:
            liabilities += -net  # 负债取贷方余额为正
            detail.setdefault('liability', []).append((a.code, -net))
        elif t in EQUITY_TYPES:
            equity += -net  # 权益取贷方余额为正
            detail.setdefault('equity', []).append((a.code, -net))
        elif t in INCOME_TYPES:
            income += -net  # 收入取贷方为正
            detail.setdefault('income', []).append((a.code, -net))
        elif t in EXPENSE_TYPES:
            expense += net   # 费用取借方为正
            detail.setdefault('expense', []).append((a.code, net))
    return assets, liabilities, equity, income, expense, detail


def _bank_balance():
    AML = env['account.move.line']
    a = _acc('1002')
    agg = AML.read_group([('account_id', '=', a.id), ('parent_state', '=', 'posted')],
                         ['debit', 'credit'], [])
    dr = sum(r['debit'] or 0.0 for r in agg)
    cr = sum(r['credit'] or 0.0 for r in agg)
    return dr - cr


def _total_diff():
    AML = env['account.move.line']
    agg = AML.read_group([('parent_state', '=', 'posted')], ['debit', 'credit'], [])
    dr = sum(r['debit'] or 0.0 for r in agg)
    cr = sum(r['credit'] or 0.0 for r in agg)
    return dr, cr, dr - cr


def main():
    env.cr.execute("SET TIME ZONE 'UTC'")
    AM = env['account.move']

    journal = _get_or_create_journal()
    acc_4001 = _get_or_create_account_4001()
    acc_1002 = _acc('1002')
    if not acc_1002:
        raise RuntimeError('未找到科目 1002 银行存款')

    # 建账前状态快照（利润表 + 银行 + 借贷平衡）
    pre_bank = _bank_balance()
    pre_dr, pre_cr, pre_diff = _total_diff()
    pre = _group_balance()
    pre_income = pre[3]
    pre_expense = pre[4]
    pre_moves = AM.search_count([('state', '=', 'posted')])
    print('--- 建账前 ---')
    print('bank(1002) net = %.2f' % pre_bank)
    print('total posted: dr=%.2f cr=%.2f diff=%.2f moves=%d' %
          (pre_dr, pre_cr, pre_diff, pre_moves))
    print('income(贷) = %.2f  expense(借) = %.2f  毛利(不含税)=%.2f' %
          (pre_income, pre_expense, pre_income - pre_expense))

    # 幂等判重
    existing = AM.search([('journal_id', '=', journal.id), ('ref', '=', REF)])
    if existing:
        print('[skip] 期初建账凭证已存在（%d 张），跳过新建' % len(existing))
        for m in existing:
            print('  move id=%d name=%r state=%s date=%s amount=%s' %
                  (m.id, m.name, m.state, m.date, m.amount_total))
    else:
        move = AM.create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': OPENING_DATE,
            'ref': REF,
            'narration': '期初建账 / Opening Balance',
            'compliance_ref': 'cas30',
            'line_ids': [
                (0, 0, {'account_id': acc_1002.id,
                        'debit': OPENING_AMOUNT, 'credit': 0.0,
                        'name': '期初银行存款'}),
                (0, 0, {'account_id': acc_4001.id,
                        'debit': 0.0, 'credit': OPENING_AMOUNT,
                        'name': '期初实收资本'}),
            ],
        })
        move.action_post()
        env.cr.commit()
        print('[move] created+posted opening entry id=%d name=%r' %
              (move.id, move.name))

    # 建账后验证
    env.invalidate_all()
    post_bank = _bank_balance()
    post_dr, post_cr, post_diff = _total_diff()
    post = _group_balance()
    assets, liabilities, equity, income, expense, detail = post
    post_moves = AM.search_count([('state', '=', 'posted')])
    pnl = income - expense

    print('--- 建账后验证 ---')
    print('bank(1002) net = %.2f  (目标 +9,228,332.70)' % post_bank)
    print('total posted: dr=%.2f cr=%.2f diff=%.2f moves=%d (+%d)' %
          (post_dr, post_cr, post_diff, post_moves, post_moves - pre_moves))
    print('资产 = %.2f' % assets)
    print('负债 = %.2f' % liabilities)
    print('权益(科目) = %.2f' % equity)
    print('本年损益(收入-费用) = %.2f' % pnl)
    print('权益合计(权益+本年损益) = %.2f' % (equity + pnl))
    print('平衡校验: 资产 - 负债 - 权益合计 = %.2f (期望 0.00)' %
          (assets - liabilities - (equity + pnl)))
    print('利润表校验: 收入 %.2f / 费用 %.2f（建账前 %.2f / %.2f）→ 不变=%s' %
          (income, expense, pre_income, pre_expense,
           abs(income - pre_income) < 0.005 and abs(expense - pre_expense) < 0.005))

    print('--- 权益科目明细 ---')
    for code, net in sorted(detail.get('equity', []), key=lambda x: (x[0] or '')):
        print('  %s = %.2f' % (code, net))
    print('========== 期初建账完成 ==========')


if __name__ == '__main__':
    main()
