# -*- coding: utf-8 -*-
"""
BS-14 修正补充脚本（幂等）：
  1. 负收入（in_com_quo_sum < 0 的 897 个团）：补记负数收入，使 6001.01 收敛到 250,130,613
     借 6001.01 净额 / 借 2221.01 税 / 贷 2203.01 或 1122.01（含税）
  2. 残留 6001.02 冲销：重复 out_invoice 团（inv_map 只取一单）的剩余 6001.02 贷方冲销
     借 6001.02 / 借 2221.01 / 贷 1122.01
"""
import datetime
from collections import defaultdict

GROSS = ('1', '12', '13', '14', '15')
VAT_RATE = 6.0
REF_RN = 'BS14-RN'   # 负收入
REF_RR = 'BS14-RR'   # 残留冲销
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


def _flush(pending, today, journal, compliance):
    moves = env['account.move'].create(pending)
    moves.action_post()
    env.cr.commit()
    env.invalidate_all()


def stage_negative_revenue(cfg):
    """负收入团：补记负数收入（借 6001.01/借 2221.01/贷 往来）。"""
    today = datetime.date.today().isoformat()
    acc_gross = cfg['acc_gross']
    acc_prepay = cfg['acc_prepay']
    acc_receivable = cfg['acc_receivable']
    acc_tax = cfg['acc_tax']

    plans = env['tour.plan'].search(
        [('biz_mode', 'in', GROSS), ('in_com_quo_sum', '<', 0)], order='id')
    total = len(plans)
    print('负收入团总数 = %d' % total, flush=True)

    existing = set(env['account.move'].search(
        [('ref', '=like', REF_RN + '-%')]).mapped('ref'))
    n_new = n_done = n_err = 0
    pending = []
    for i, p in enumerate(plans):
        ref = '%s-%d' % (REF_RN, p.id)
        if ref in existing:
            n_done += 1
            continue
        try:
            aa = p.analytic_account_id
            ana = {str(aa.id): 100.0} if aa else {}
            partner = p.supplier_id.id if p.supplier_id else False
            new_total = _round(p.in_com_quo_sum)   # 负数
            abs_total = -new_total
            new_net = round(new_total / (1 + VAT_RATE / 100.0), 2)  # 负数
            abs_net = -new_net
            abs_tax = _round(abs_total - abs_net)
            to_prepay = _round(min(max(p.sum_pay_normal or 0.0, 0.0), abs_total))
            to_receivable = _round(abs_total - to_prepay)

            lines = [(0, 0, {'account_id': acc_gross.id, 'debit': abs_net,
                             'analytic_distribution': ana,
                             'compliance_ref': 'cas14_principal',
                             'name': '冲减收入 %s' % (p.plan_code or p.id)})]
            if abs_tax > 0:
                lines.append((0, 0, {'account_id': acc_tax.id, 'debit': abs_tax,
                                     'analytic_distribution': ana,
                                     'compliance_ref': 'vat_reg',
                                     'name': '冲减销项税 %s' % (p.plan_code or p.id)}))
            if to_prepay > 0:
                lines.append((0, 0, {'account_id': acc_prepay.id, 'partner_id': partner,
                                     'credit': to_prepay,
                                     'analytic_distribution': ana,
                                     'name': '冲减预收 %s' % (p.plan_code or p.id)}))
            if to_receivable > 0:
                lines.append((0, 0, {'account_id': acc_receivable.id, 'partner_id': partner,
                                     'credit': to_receivable,
                                     'analytic_distribution': ana,
                                     'name': '冲减应收 %s' % (p.plan_code or p.id)}))

            pending.append({'move_type': 'entry', 'journal_id': cfg['journal'].id,
                            'date': today, 'ref': ref,
                            'compliance_ref': 'cas14_principal',
                            'line_ids': lines})
            n_new += 1
        except Exception as e:
            n_err += 1
            if n_err <= 20:
                print('  [err] plan %s: %s' % (p.plan_code or p.id, repr(e)[:200]), flush=True)
        if len(pending) >= BATCH:
            _flush(pending, today, cfg['journal'], 'cas14_principal')
            pending = []
            print('  neg progress %d/%d (new=%d done=%d err=%d)' %
                  (i + 1, total, n_new, n_done, n_err), flush=True)
    if pending:
        _flush(pending, today, cfg['journal'], 'cas14_principal')
    env.cr.commit()
    print('=== 负收入完成：new=%d done=%d err=%d ===' % (n_new, n_done, n_err), flush=True)


def stage_residual_reversal(cfg):
    """残留 6001.02 冲销：对仍有 6001.02 净贷余额的团，冲销其未反转的一张 out_invoice。

    残留 = 主脚本 inv_map 只取一单，导致重复发票团的第二张发票未反转。
    此处按团反转「恰好一张」仍有 6001.02 贷方的发票，使该团 6001.02 归零。
    """
    today = datetime.date.today().isoformat()
    acc_dt = cfg['acc_dt']
    acc_receivable = cfg['acc_receivable']
    acc_tax = cfg['acc_tax']

    existing = set(env['account.move'].search(
        [('ref', '=like', REF_RR + '-%')]).mapped('ref'))

    # 找出仍有 6001.02 净贷的团（按 analytic）
    resid_by_analytic = defaultdict(float)
    for ln in env['account.move.line'].search([
            ('account_id', '=', acc_dt.id), ('parent_state', '=', 'posted')]):
        net = ln.credit - ln.debit
        for al in ln.analytic_line_ids:
            resid_by_analytic[al.account_id.id] += net

    aa_ids = [aa for aa, net in resid_by_analytic.items() if net > 0.01]
    plans = env['tour.plan'].search(
        [('biz_mode', 'in', GROSS), ('analytic_account_id', 'in', aa_ids)], order='id')
    print('残留 6001.02 团数 = %d' % len(plans), flush=True)

    n_new = n_done = n_err = 0
    for p in plans:
        ref = '%s-%d' % (REF_RR, p.id)
        if ref in existing:
            n_done += 1
            continue
        try:
            aa = p.analytic_account_id
            ana = {str(aa.id): 100.0} if aa else {}
            partner = p.supplier_id.id if p.supplier_id else False
            invoices = env['account.move'].search([
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
                ('tour_plan_id', '=', p.id)])
            for mv in invoices:
                rev_net = _round(sum(
                    ln.credit - ln.debit for ln in mv.line_ids
                    if ln.account_id.id == acc_dt.id))
                if rev_net < 0.01:
                    continue
                rev_tax = _round(sum(
                    ln.credit - ln.debit for ln in mv.line_ids
                    if ln.account_id.id == acc_tax.id))
                rev_recv = _round(sum(
                    ln.debit - ln.credit for ln in mv.line_ids
                    if ln.account_id.id == acc_receivable.id))
                lines = []
                if rev_net > 0:
                    lines.append((0, 0, {'account_id': acc_dt.id, 'debit': rev_net,
                                         'analytic_distribution': ana,
                                         'compliance_ref': 'cas14_agent',
                                         'name': '冲销残留净额法收入 %s' % (p.plan_code or p.id)}))
                if rev_tax > 0:
                    lines.append((0, 0, {'account_id': acc_tax.id, 'debit': rev_tax,
                                         'analytic_distribution': ana,
                                         'compliance_ref': 'vat_reg',
                                         'name': '冲销残留销项税 %s' % (p.plan_code or p.id)}))
                if rev_recv > 0:
                    lines.append((0, 0, {'account_id': acc_receivable.id, 'partner_id': partner,
                                         'credit': rev_recv,
                                         'analytic_distribution': ana,
                                         'name': '冲销残留应收 %s' % (p.plan_code or p.id)}))
                if lines:
                    m = env['account.move'].create({
                        'move_type': 'entry', 'journal_id': cfg['journal'].id,
                        'date': today, 'ref': ref, 'compliance_ref': 'cas14_agent',
                        'line_ids': lines})
                    m.action_post()
                    n_new += 1
                break  # 只反转一张发票（=残留量）
        except Exception as e:
            n_err += 1
            print('  [err] plan %s: %s' % (p.plan_code or p.id, repr(e)[:200]), flush=True)
    env.cr.commit()
    print('=== 残留冲销完成：new=%d done=%d err=%d ===' % (n_new, n_done, n_err), flush=True)


def main():
    cfg = {
        'journal': _journal(),
        'acc_gross': _acc('6001.01'),
        'acc_dt': _acc('6001.02'),
        'acc_prepay': _acc('2203.01'),
        'acc_receivable': _acc('1122.01'),
        'acc_tax': _acc('2221.01'),
    }
    stage_negative_revenue(cfg)
    stage_residual_reversal(cfg)
    print('========== BS-14 补充完成 ==========', flush=True)


if __name__ == '__main__':
    main()
