# -*- coding: utf-8 -*-
"""
BS-14 收入成本确认口径修正脚本（冲销重记，幂等，批量优化）。

在 Odoo shell 中运行（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < fix_bs14.py

修正内容 [BS-14 §五]：
  A. 收入侧（按团，总额法重记）：
     - 冲销误记到 6001.02 的净额法收入（旧净额 + 旧销项税 + 旧往来 counterpart）
     - 补记 6001.01 全额收入（biz_mode 1/12/13/14/15，in_com_quo_sum 含税全额，拆税）
     - 补记 counterpart 拆分为：已收部分→2203.01 预收、未收部分→1122.01 应收
  B. 成本侧（按团）：41 代订成本 out_sum 从 6401 转出 → 2241.01 代收代付
     - 贷 6401 / 借 2241.01

幂等依据：correction move ref 前缀 BS14-RC-（收入）/ BS14-CC-（成本），判重跳过。
借贷平衡：每个凭证借=贷（由金额构造保证）。
批量：累计 move_vals 后 create + action_post，减少逐团 ORM 开销。
"""
import datetime
import sys
from collections import defaultdict

GROSS = ('1', '12', '13', '14', '15')
VAT_RATE = 6.0
REF_RC = 'BS14-RC'
REF_CC = 'BS14-CC'
BATCH = 1000


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
    if not j:
        raise RuntimeError('未找到可用日记账')
    return j


def _flush(move_vals, today, journal, compliance):
    """批量 create + post + commit。"""
    Move = env['account.move']
    moves = Move.create(move_vals)
    moves.action_post()
    env.cr.commit()
    env.invalidate_all()
    return len(moves)


def stage_revenue(cfg):
    today = datetime.date.today().isoformat()
    acc_gross = cfg['acc_gross']
    acc_dt = cfg['acc_dt']
    acc_prepay = cfg['acc_prepay']
    acc_receivable = cfg['acc_receivable']
    acc_tax = cfg['acc_tax']

    plans = env['tour.plan'].search([('biz_mode', 'in', GROSS)], order='id')
    total = len(plans)
    print('收入侧：GROSS 团总数 = %d' % total, flush=True)

    inv_map = {}
    for m in env['account.move'].search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('tour_plan_id', '!=', False)]):
        inv_map[m.tour_plan_id.id] = m

    existing_refs = set(
        env['account.move'].search([('ref', '=like', REF_RC + '-%')]).mapped('ref'))

    n_done = n_new = n_skip = n_err = 0
    pending = []
    for i, p in enumerate(plans):
        ref = '%s-%d' % (REF_RC, p.id)
        if ref in existing_refs:
            n_done += 1
            continue
        try:
            old_move = p.income_move_id or inv_map.get(p.id)
            old_net = old_tax = 0.0
            old_counterpart = None
            if old_move:
                for ln in old_move.line_ids:
                    if ln.account_id.id == acc_dt.id:
                        old_net += ln.credit - ln.debit
                    elif ln.account_id.id == acc_tax.id:
                        old_tax += ln.credit - ln.debit
                old_total = _round(old_net + old_tax)
                if old_total > 0:
                    old_counterpart = (acc_prepay if p.income_move_id else acc_receivable,
                                       old_total)

            new_total = _round(p.in_com_quo_sum)
            if old_net == 0.0 and old_tax == 0.0 and new_total <= 0:
                n_skip += 1
                continue

            aa = p.analytic_account_id
            ana = {str(aa.id): 100.0} if aa else {}
            partner = p.supplier_id.id if p.supplier_id else False

            new_net = round(new_total / (1 + VAT_RATE / 100.0), 2)
            new_tax = _round(new_total - new_net)
            to_prepay = _round(min(max(p.sum_pay_normal or 0.0, 0.0), new_total))
            to_receivable = _round(new_total - to_prepay)

            lines = []
            if old_net > 0:
                lines.append((0, 0, {'account_id': acc_dt.id, 'partner_id': partner,
                                     'debit': _round(old_net),
                                     'analytic_distribution': ana,
                                     'compliance_ref': 'cas14_agent',
                                     'name': '冲销净额法收入 %s' % (p.plan_code or p.id)}))
            if old_tax > 0:
                lines.append((0, 0, {'account_id': acc_tax.id,
                                     'debit': _round(old_tax),
                                     'analytic_distribution': ana,
                                     'compliance_ref': 'vat_reg',
                                     'name': '冲销旧销项税 %s' % (p.plan_code or p.id)}))
            if old_counterpart and old_counterpart[1] > 0:
                lines.append((0, 0, {'account_id': old_counterpart[0].id,
                                     'partner_id': partner,
                                     'credit': old_counterpart[1],
                                     'analytic_distribution': ana,
                                     'name': '冲销旧往来 %s' % (p.plan_code or p.id)}))
            if to_prepay > 0:
                lines.append((0, 0, {'account_id': acc_prepay.id, 'partner_id': partner,
                                     'debit': to_prepay,
                                     'analytic_distribution': ana,
                                     'name': '结转预收 %s' % (p.plan_code or p.id)}))
            if to_receivable > 0:
                lines.append((0, 0, {'account_id': acc_receivable.id, 'partner_id': partner,
                                     'debit': to_receivable,
                                     'analytic_distribution': ana,
                                     'name': '确认应收 %s' % (p.plan_code or p.id)}))
            if new_net > 0:
                lines.append((0, 0, {'account_id': acc_gross.id,
                                     'credit': new_net,
                                     'analytic_distribution': ana,
                                     'compliance_ref': 'cas14_principal',
                                     'name': '确认收入(不含税) %s' % (p.plan_code or p.id)}))
            if new_tax > 0:
                lines.append((0, 0, {'account_id': acc_tax.id,
                                     'credit': new_tax,
                                     'analytic_distribution': ana,
                                     'compliance_ref': 'vat_reg',
                                     'name': '销项税额 %s' % (p.plan_code or p.id)}))

            if not lines:
                n_skip += 1
                continue

            pending.append({
                'move_type': 'entry',
                'journal_id': cfg['journal'].id,
                'date': today,
                'ref': ref,
                'compliance_ref': 'cas14_principal',
                'line_ids': lines,
            })
            n_new += 1
        except Exception as e:
            n_err += 1
            if n_err <= 30:
                print('  [err] plan %s: %s' % (p.plan_code or p.id, repr(e)[:200]), flush=True)

        if len(pending) >= BATCH:
            _flush(pending, today, cfg['journal'], 'cas14_principal')
            pending = []
            print('  revenue progress %d/%d (new=%d done=%d skip=%d err=%d)' %
                  (i + 1, total, n_new, n_done, n_skip, n_err), flush=True)

    if pending:
        _flush(pending, today, cfg['journal'], 'cas14_principal')
    env.cr.commit()
    print('=== 收入侧完成：new=%d done(已处理)=%d skip=%d err=%d ===' %
          (n_new, n_done, n_skip, n_err), flush=True)


def stage_cost(cfg):
    today = datetime.date.today().isoformat()
    acc_cost = cfg['acc_cost']
    acc_dd_payable = cfg['acc_dd_payable']

    plans = env['tour.plan'].search([('biz_mode', '=', '41')], order='id')
    total = len(plans)
    print('成本侧：41 团总数 = %d' % total, flush=True)

    cost_by_analytic = defaultdict(float)
    for ln in env['account.move.line'].search([
            ('account_id', '=', acc_cost.id), ('parent_state', '=', 'posted')]):
        amt = ln.debit - ln.credit
        for al in ln.analytic_line_ids:
            cost_by_analytic[al.account_id.id] += amt

    existing_refs = set(
        env['account.move'].search([('ref', '=like', REF_CC + '-%')]).mapped('ref'))

    n_done = n_new = n_skip = n_err = 0
    pending = []
    for i, p in enumerate(plans):
        ref = '%s-%d' % (REF_CC, p.id)
        if ref in existing_refs:
            n_done += 1
            continue
        try:
            aa = p.analytic_account_id
            amt = _round(cost_by_analytic.get(aa.id, 0.0)) if aa else 0.0
            if amt <= 0:
                n_skip += 1
                continue
            ana = {str(aa.id): 100.0} if aa else {}
            partner = p.supplier_id.id if p.supplier_id else False
            pending.append({
                'move_type': 'entry',
                'journal_id': cfg['journal'].id,
                'date': today,
                'ref': ref,
                'compliance_ref': 'cas14_agent',
                'line_ids': [
                    (0, 0, {'account_id': acc_cost.id, 'credit': amt,
                            'analytic_distribution': ana,
                            'compliance_ref': 'cas14_agent',
                            'name': '转出代订成本 %s' % (p.plan_code or p.id)}),
                    (0, 0, {'account_id': acc_dd_payable.id, 'partner_id': partner,
                            'debit': amt, 'analytic_distribution': ana,
                            'compliance_ref': 'cas14_agent',
                            'name': '代收代付 %s' % (p.plan_code or p.id)}),
                ],
            })
            n_new += 1
        except Exception as e:
            n_err += 1
            if n_err <= 30:
                print('  [err] plan %s: %s' % (p.plan_code or p.id, repr(e)[:200]), flush=True)

        if len(pending) >= BATCH:
            _flush(pending, today, cfg['journal'], 'cas14_agent')
            pending = []
            print('  cost progress %d/%d (new=%d done=%d skip=%d err=%d)' %
                  (i + 1, total, n_new, n_done, n_skip, n_err), flush=True)

    if pending:
        _flush(pending, today, cfg['journal'], 'cas14_agent')
    env.cr.commit()
    print('=== 成本侧完成：new=%d done(已处理)=%d skip=%d err=%d ===' %
          (n_new, n_done, n_skip, n_err), flush=True)


def main():
    cfg = {
        'journal': _journal(),
        'acc_gross': _acc('6001.01'),
        'acc_dt': _acc('6001.02'),
        'acc_prepay': _acc('2203.01'),
        'acc_receivable': _acc('1122.01'),
        'acc_tax': _acc('2221.01'),
        'acc_cost': _acc('6401'),
        'acc_dd_payable': _acc('2241.01'),
    }
    stage = (env.context.get('bs14_stage') or 'both').lower()
    if stage in ('revenue', 'both'):
        stage_revenue(cfg)
    if stage in ('cost', 'both'):
        stage_cost(cfg)
    print('========== BS-14 修正完成 ==========', flush=True)
    print('posted account.move = %d' % env['account.move'].search_count([('state', '=', 'posted')]), flush=True)


if __name__ == '__main__':
    main()
