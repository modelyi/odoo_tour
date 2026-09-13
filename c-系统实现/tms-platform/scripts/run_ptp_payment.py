# -*- coding: utf-8 -*-
"""
P2P Phase 2：供应商合并付款 + 批量核销（独立脚本，Phase 1 已完成后运行）

在 Odoo shell 中运行：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < run_ptp_payment.py

按供应商归并：879 家供应商 → 每家 1 张付款单（借 2202 应付 / 贷 1002 银行），
批量核销该供应商全部未付 vendor bill（account.move.line.reconcile）。

幂等：只处理 payment_state != 'paid' 的账单，重跑 created=0。
"""
import datetime
from collections import defaultdict

ACCOUNT_PAYABLE = '2202'
ACCOUNT_BANK = '1002'


def setup():
    bank_journal = env['account.journal'].search([('type', '=', 'bank')], limit=1)
    acc_payable = env['account.account'].search([('code', '=', ACCOUNT_PAYABLE)], limit=1)
    acc_bank = env['account.account'].search([('code', '=', ACCOUNT_BANK)], limit=1)
    assert bank_journal and acc_payable and acc_bank, '基础配置缺失'
    if bank_journal.default_account_id.id != acc_bank.id:
        bank_journal.default_account_id = acc_bank.id
    pml = env['account.payment.method.line'].search(
        [('payment_type', '=', 'outbound'), ('journal_id', '=', bank_journal.id)], limit=1)
    if not pml:
        pml = env['account.payment.method.line'].search(
            [('payment_type', '=', 'outbound')], limit=1)
    assert pml, '无可用付款方式'
    if pml.payment_account_id.id != acc_bank.id:
        pml.payment_account_id = acc_bank.id
    return dict(bank_journal=bank_journal, pml=pml,
                acc_payable=acc_payable, acc_bank=acc_bank)


def main():
    cfg = setup()
    today = datetime.date.today().isoformat()

    # 补索引（account_move.tour_plan_id 无索引，供后续按团查询加速）
    env.cr.execute(
        'CREATE INDEX IF NOT EXISTS account_move_tour_plan_id_idx ON account_move(tour_plan_id)')
    env.cr.commit()

    # 单条 SQL 取全部未付账单，按供应商归并（避免无索引的 ORM 嵌套查询）
    env.cr.execute("""
        SELECT p.supplier_id, m.id
        FROM account_move m
        JOIN tour_plan p ON p.id = m.tour_plan_id
        WHERE m.move_type = 'in_invoice' AND m.state = 'posted'
          AND m.payment_state != 'paid'
        ORDER BY p.supplier_id, m.id
    """)
    rows = env.cr.fetchall()
    by_sup = defaultdict(list)
    for sup_id, bill_id in rows:
        by_sup[sup_id].append(bill_id)
    print('suppliers with unpaid bills=%d, unpaid bills=%d' % (len(by_sup), len(rows)))

    n_pay = n_settle = 0
    items = sorted(by_sup.items())
    for i, (sup_id, bill_ids) in enumerate(items):
        bills = env['account.move'].browse(bill_ids)
        total = round(sum(bills.mapped('amount_total')), 2)
        if total <= 0:
            continue
        pay = env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': sup_id,
            'amount': total,
            'journal_id': cfg['bank_journal'].id,
            'payment_method_line_id': cfg['pml'].id,
            'destination_account_id': cfg['acc_payable'].id,
            'date': today,
        })
        pay.action_post()
        # 批量核销：付款单 2202 借方 vs 全部账单 2202 贷方
        p_line = pay.move_id.line_ids.filtered(
            lambda l: l.account_id.id == cfg['acc_payable'].id and l.debit > 0 and not l.reconciled)
        b_lines = bills.mapped('line_ids').filtered(
            lambda l: l.account_id.id == cfg['acc_payable'].id and not l.reconciled)
        if p_line and b_lines:
            (p_line | b_lines).reconcile()
        # 联动请款单：payment_id + approved→paid
        prs = env['tour.pay.request'].search([('bill_id', 'in', bill_ids)])
        prs.write({'payment_id': pay.id})
        prs.filtered(lambda r: r.state == 'approved').action_pay()
        n_pay += 1
        n_settle += len(bills)
        if (i + 1) % 50 == 0:
            env.cr.commit()
            env.invalidate_all()
            print('  progress %d/%d (payment=%d settled=%d)' % (
                i + 1, len(items), n_pay, n_settle))
    env.cr.commit()
    print('========== Phase 2 完成 ==========')
    print('payments created=%d, bills settled=%d' % (n_pay, n_settle))
    print('total payments=%d' % env['account.payment'].search_count([]))
    print('paid bills=%d / %d' % (
        env['account.move'].search_count([('move_type', '=', 'in_invoice'), ('payment_state', '=', 'paid')]),
        env['account.move'].search_count([('move_type', '=', 'in_invoice')])))


if __name__ == '__main__':
    main()
