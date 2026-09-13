# -*- coding: utf-8 -*-
"""
P2P 采购到付款全链路植入脚本（Procure to Pay）——批量优化版

在 Odoo shell 中运行（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < run_ptp_posting.py

链路：
  成本合计 out_sum > 0 且 supplier_id 非空 →
    Phase 1（按团批量，幂等 + 断点续跑）：
      ① vendor bill（account.move in_invoice）：借 6401 主营业务成本 / 贷 2202 应付账款，挂团分析账户
      ② 请款单（tour.pay.request）：分级审批 state 机（免审≤1000 / 一级≤5万 / 二级≤20万 / 三级>20万双签）
    Phase 2（按供应商归并，幂等）：
      ③ 供应商合并付款（account.payment）：借 2202 应付 / 贷 1002 银行存款
      ④ 批量核销该供应商全部 vendor bill（account.move.line.reconcile）

成本侧无分项（源 CSV 仅 OutSum 合计），成本总额统一挂 6401 主营业务成本；应付统一挂 2202。
付款按供应商归并：879 家供应商 → 879 张付款单（合并付款），核销该供应商全部应付账单。

幂等依据：plan.cost_bill_id（账单）、tour.pay.request(plan_id)、bill.payment_state（付款核销）。
断点续跑：ptp_checkpoint.txt 记录 Phase 1 最后处理 plan.id。
"""
import os

CHECKPOINT = '/var/lib/odoo/ptp_checkpoint.txt'
BATCH = 500
ACCOUNT_COST = '6401'    # 主营业务成本（无分项统一）
ACCOUNT_PAYABLE = '2202'  # 应付账款
ACCOUNT_BANK = '1002'     # 银行存款


def get_checkpoint():
    try:
        with open(CHECKPOINT) as fh:
            return int((fh.read().strip() or '0'))
    except Exception:
        return 0


def set_checkpoint(pid):
    with open(CHECKPOINT, 'w') as fh:
        fh.write(str(pid))


def setup():
    product = env['product.product'].search([], limit=1)
    purchase_journal = env['account.journal'].search([('type', '=', 'purchase')], limit=1)
    bank_journal = env['account.journal'].search([('type', '=', 'bank')], limit=1)
    acc_cost = env['account.account'].search([('code', '=', ACCOUNT_COST)], limit=1)
    acc_payable = env['account.account'].search([('code', '=', ACCOUNT_PAYABLE)], limit=1)
    acc_bank = env['account.account'].search([('code', '=', ACCOUNT_BANK)], limit=1)
    assert product and purchase_journal and bank_journal, '基础配置缺失（product/purchase journal/bank journal）'
    assert acc_cost and acc_payable and acc_bank, '科目表缺失（6401/2202/1002）'
    # 付款资金账户落 1002 银行存款：outstanding_account_id 取自
    # payment_method_line_id.payment_account_id，显式指向 1002 [TDS §2.3]
    if bank_journal.default_account_id.id != acc_bank.id:
        bank_journal.default_account_id = acc_bank.id
    pml = env['account.payment.method.line'].search(
        [('payment_type', '=', 'outbound'), ('journal_id', '=', bank_journal.id)], limit=1)
    if not pml:
        pml = env['account.payment.method.line'].search(
            [('payment_type', '=', 'outbound')], limit=1)
    assert pml, '无可用付款方式（outbound payment method line）'
    if pml.payment_account_id.id != acc_bank.id:
        pml.payment_account_id = acc_bank.id
    return dict(product=product, purchase_journal=purchase_journal,
                bank_journal=bank_journal, pml=pml,
                acc_cost=acc_cost, acc_payable=acc_payable, acc_bank=acc_bank)


def phase1_bills_and_requests(cfg, today):
    """Phase 1：批量生成 vendor bill + 请款单（幂等，断点续跑）。"""
    cp = get_checkpoint()
    max_plans = int(os.environ.get('PTP_MAX_PLANS', '0') or 0)
    print('Phase 1 checkpoint from=%d' % cp)
    domain = [
        ('id', '>', cp),
        ('out_sum', '>', 0),
        ('supplier_id', '!=', False),
        ('cost_bill_id', '=', False),
    ]
    # 分批取（每批 BATCH 个，处理完再取下一批，避免一次性装载 8 万团）
    n_bill = n_pr = n_skip = n_err = 0
    total = env['tour.plan'].search_count(domain)
    print('Phase 1 eligible plans=%d%s' % (total, (' (capped)' if max_plans else '')))
    done = 0
    last_id = cp
    while True:
        plans = env['tour.plan'].search(domain, order='id', limit=BATCH)
        if not plans:
            break
        # 确保分析账户（绝大多数 O2C 已建，快速 no-op）
        for p in plans:
            p._ensure_analytic_account()
        # ① 批量建 vendor bill
        bill_vals = []
        for p in plans:
            aa = p.analytic_account_id
            amt = round(float(p.out_sum or 0.0), 2)
            if amt <= 0:
                continue
            bill_vals.append({
                'move_type': 'in_invoice',
                'partner_id': p.supplier_id.id,
                'journal_id': cfg['purchase_journal'].id,
                'invoice_date': p.end_date or today,
                'tour_plan_id': p.id,
                'ref': 'P2P-%s' % (p.plan_code or p.id),
                'compliance_ref': 'cas1',
                'invoice_line_ids': [(0, 0, {
                    'product_id': cfg['product'].id,
                    'name': '成本 %s' % (p.plan_code or p.id),
                    'quantity': 1.0,
                    'price_unit': amt,
                    'account_id': cfg['acc_cost'].id,
                    'analytic_distribution': {str(aa.id): 100.0},
                    'tax_ids': [(6, 0, [])],
                })],
            })
        bills = env['account.move'].create(bill_vals)
        # 强制应付行落 2202 + 挂团分析账户（批量写）
        bills.mapped('line_ids').filtered(
            lambda l: l.account_id.account_type == 'liability_payable').write({
                'account_id': cfg['acc_payable'].id})
        bills.action_post()
        # 回写 plan.cost_bill_id
        plan_by_bill = {}
        for b in bills:
            plan_by_bill[b.tour_plan_id.id] = b.id
        # ② 批量建请款单
        pr_vals = []
        for p in plans:
            bid = plan_by_bill.get(p.id)
            if not bid:
                n_skip += 1
                continue
            amt = round(float(p.out_sum or 0.0), 2)
            pr_vals.append({
                'plan_id': p.id,
                'supplier_id': p.supplier_id.id,
                'bill_id': bid,
                'amount': amt,
                'cost_type': 'other',
                'cost_account_id': cfg['acc_cost'].id,
                'reason': '团成本应付 %s' % (p.plan_code or p.id),
                'apply_date': bills.filtered(lambda b: b.id == bid).invoice_date or today,
            })
        prs = env['tour.pay.request'].create(pr_vals)
        prs.action_approve()
        n_bill += len(bills)
        n_pr += len(prs)
        # 回写 cost_bill_id（ORM 写，invalidate 后释放）
        for b in bills:
            b.tour_plan_id.cost_bill_id = b.id
        done += len(plans)
        last_id = plans[-1].id
        env.cr.commit()
        env.invalidate_all()
        set_checkpoint(last_id)
        print('  Phase 1 progress %d/%d (bill=%d payreq=%d skip=%d err=%d)' % (
            done, total, n_bill, n_pr, n_skip, n_err))
        if max_plans and done >= max_plans:
            break
    print('Phase 1 完成：bill=%d payreq=%d skip=%d err=%d' % (n_bill, n_pr, n_skip, n_err))


def phase2_payments(cfg, today):
    """Phase 2：按供应商归并付款 + 批量核销（幂等：payment_state）。"""
    print('Phase 2：供应商合并付款 + 核销')
    # 找出仍有未付账单的供应商
    env.cr.execute("""
        SELECT DISTINCT p.supplier_id
        FROM tour_plan p
        JOIN account_move m ON m.tour_plan_id = p.id
        WHERE m.move_type = 'in_invoice' AND m.state = 'posted'
          AND m.payment_state != 'paid'
        ORDER BY p.supplier_id
    """)
    suppliers = [r[0] for r in env.cr.fetchall()]
    print('suppliers with unpaid bills=%d' % len(suppliers))
    n_pay = n_rec = 0
    for i, sup_id in enumerate(suppliers):
        bills = env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid'),
            ('tour_plan_id.supplier_id', '=', sup_id),
        ])
        if not bills:
            continue
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
        # 批量核销：付款单 2202 借方 与 全部账单 2202 贷方
        p_line = pay.move_id.line_ids.filtered(
            lambda l: l.account_id.id == cfg['acc_payable'].id and l.debit > 0 and not l.reconciled)
        b_lines = bills.mapped('line_ids').filtered(
            lambda l: l.account_id.id == cfg['acc_payable'].id and not l.reconciled)
        if p_line and b_lines:
            (p_line | b_lines).reconcile()
        # 联动请款单：payment_id + 状态 approved→paid
        prs = env['tour.pay.request'].search([
            ('supplier_id', '=', sup_id),
            ('bill_id', 'in', bills.ids),
        ])
        prs.write({'payment_id': pay.id})
        prs.filtered(lambda r: r.state == 'approved').action_pay()
        n_pay += 1
        n_rec += len(bills)
        if (i + 1) % 100 == 0:
            env.cr.commit()
            env.invalidate_all()
            print('  Phase 2 progress %d/%d (payment=%d bills_settled=%d)' % (
                i + 1, len(suppliers), n_pay, n_rec))
    env.cr.commit()
    print('Phase 2 完成：payment=%d bills_settled=%d' % (n_pay, n_rec))


def main():
    import datetime
    cfg = setup()
    today = datetime.date.today().isoformat()
    phase1_bills_and_requests(cfg, today)
    phase2_payments(cfg, today)
    print('========== P2P 完成 ==========')
    print('vendor bills=%d' % env['account.move'].search_count([('move_type', '=', 'in_invoice')]))
    print('pay requests=%d' % env['tour.pay.request'].search_count([]))
    print('payments=%d' % env['account.payment'].search_count([]))
    print('posted account.move=%d' % env['account.move'].search_count([('state', '=', 'posted')]))
    print('posted move.line=%d' % env['account.move.line'].search_count([('parent_state', '=', 'posted')]))


if __name__ == '__main__':
    main()
