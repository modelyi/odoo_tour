# -*- coding: utf-8 -*-
"""
BS-14 补充：负成本团（out_sum < 0）补记，使 6401 收敛到 255,423,213（含税口径）。

P2P 仅过账 out_sum > 0 且 supplier 非空的团，负成本（670 团，-325,405.85）被跳过。
为与负收入口径一致（BS-14 §六 6401=255,423,213 = Σ out_sum 全量），补记：
    贷 6401 主营业务成本 / 借 2202 应付账款（供应商退款/成本冲减）
幂等：ref 前缀 BS14-NC-。
"""
import datetime

GROSS = ('1', '12', '13', '14', '15')
REF_NC = 'BS14-NC'
BATCH = 500


def _acc(code):
    a = env['account.account'].search([('code', '=', code)], limit=1)
    if not a:
        raise RuntimeError('未找到科目 %s' % code)
    return a


def _round(x):
    return round(float(x or 0.0), 2)


def _journal():
    j = env['account.journal'].search([('type', '=', 'general')], limit=1)
    if not j:
        j = env['account.journal'].search([], limit=1)
    return j


def main():
    today = datetime.date.today().isoformat()
    acc_cost = _acc('6401')
    acc_payable = _acc('2202')
    journal = _journal()

    plans = env['tour.plan'].search(
        [('biz_mode', 'in', GROSS), ('out_sum', '<', 0)], order='id')
    total = len(plans)
    print('负成本团总数 = %d' % total, flush=True)

    existing = set(env['account.move'].search(
        [('ref', '=like', REF_NC + '-%')]).mapped('ref'))
    n_new = n_done = n_err = 0
    pending = []
    for i, p in enumerate(plans):
        ref = '%s-%d' % (REF_NC, p.id)
        if ref in existing:
            n_done += 1
            continue
        try:
            aa = p.analytic_account_id
            ana = {str(aa.id): 100.0} if aa else {}
            partner = p.supplier_id.id if p.supplier_id else False
            amt = _round(-p.out_sum)
            if amt <= 0:
                continue
            pending.append({
                'move_type': 'entry', 'journal_id': journal.id,
                'date': today, 'ref': ref, 'compliance_ref': 'cas1',
                'line_ids': [
                    (0, 0, {'account_id': acc_cost.id, 'credit': amt,
                            'analytic_distribution': ana, 'compliance_ref': 'cas1',
                            'name': '冲减成本 %s' % (p.plan_code or p.id)}),
                    (0, 0, {'account_id': acc_payable.id, 'partner_id': partner,
                            'debit': amt, 'analytic_distribution': ana,
                            'compliance_ref': 'cas1',
                            'name': '供应商成本冲减 %s' % (p.plan_code or p.id)}),
                ],
            })
            n_new += 1
        except Exception as e:
            n_err += 1
            if n_err <= 20:
                print('  [err] plan %s: %s' % (p.plan_code or p.id, repr(e)[:200]), flush=True)
        if len(pending) >= BATCH:
            moves = env['account.move'].create(pending)
            moves.action_post()
            env.cr.commit()
            env.invalidate_all()
            pending = []
            print('  negcost progress %d/%d (new=%d done=%d err=%d)' %
                  (i + 1, total, n_new, n_done, n_err), flush=True)
    if pending:
        moves = env['account.move'].create(pending)
        moves.action_post()
    env.cr.commit()
    print('=== 负成本完成：new=%d done=%d err=%d ===' % (n_new, n_done, n_err), flush=True)


if __name__ == '__main__':
    main()
