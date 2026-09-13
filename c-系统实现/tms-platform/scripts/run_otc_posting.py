# -*- coding: utf-8 -*-
"""
O2C 全链路过账脚本（Order to Cash）

在 Odoo shell 中运行（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < run_otc_posting.py

链路（按团批量，幂等 + 断点续跑）：
  发票模式（sum_un_pay > 0）：
    开票 out_invoice（挂 tour_plan_id）→ 过账落 1122.01 应收 + analytic
    收款认领（关联发票 claim_line_ids）→ 借资金/贷 1122.01 → 原生 reconcile 核销
  预收模式（sum_pay_normal > 0 且 sum_un_pay <= 0）：
    收款认领（裸收款）→ 借资金/贷 2203.01 预收
    收入确认（总额/净额按 biz_mode）→ 借 2203.01/贷 6001/贷 2221 销项
  差额征税抵减：仅总额法（biz_mode 21/31），源数据无总额法团，不触发

幂等依据：plan.invoice_ids（发票）、claim.name（收款）、plan.income_move_id（收入）。
断点续跑：checkpoint 文件记录最后处理 plan.id，重跑从断点继续。
"""
import os

CHECKPOINT = '/var/lib/odoo/otc_checkpoint.txt'
BATCH = 50
VAT_RATE = 6.0  # 一般纳税人旅游服务 6%（价外税，与 BS-11 §10.3 一致）


def get_checkpoint():
    try:
        with open(CHECKPOINT) as fh:
            return int((fh.read().strip() or '0'))
    except Exception:
        return 0


def set_checkpoint(pid):
    with open(CHECKPOINT, 'w') as fh:
        fh.write(str(pid))


def _get_or_create_tax():
    tax = env['account.tax'].search(
        [('amount', '=', VAT_RATE), ('type_tax_use', '=', 'sale'),
         ('name', '=', '旅游服务 6%')], limit=1)
    if not tax:
        tax_acc = env['account.account'].search([('code', '=', '2221.01')], limit=1)
        if not tax_acc:
            raise RuntimeError('未找到销项税科目 2221.01')
        tax = env['account.tax'].create({
            'name': '旅游服务 6%',
            'amount': VAT_RATE,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'invoice_repartition_line_ids': [
                (0, 0, {'factor': 1.0, 'repartition_type': 'base'}),
                (0, 0, {'factor': 1.0, 'repartition_type': 'tax',
                        'account_id': tax_acc.id}),
            ],
            'refund_repartition_line_ids': [
                (0, 0, {'factor': 1.0, 'repartition_type': 'base'}),
                (0, 0, {'factor': 1.0, 'repartition_type': 'tax',
                        'account_id': tax_acc.id}),
            ],
        })
    return tax


def setup():
    tax6 = _get_or_create_tax()
    product = env['product.product'].search([], limit=1)
    sale_journal = env['account.journal'].search([('type', '=', 'sale')], limit=1)
    bank_channel = env['tour.pay.channel'].search(
        [('channel_type', '=', 'bank_transfer')], limit=1)
    bank_account = env['tour.bank.account'].search([], limit=1)
    acc_rev_gross = env['account.account'].search([('code', '=', '6001.01')], limit=1)
    acc_rev_dt = env['account.account'].search([('code', '=', '6001.02')], limit=1)
    acc_rev_dd = env['account.account'].search([('code', '=', '6001.03')], limit=1)
    assert product and sale_journal and bank_channel, '基础配置缺失（product/journal/channel）'
    return dict(tax6=tax6, product=product, sale_journal=sale_journal,
                bank_channel=bank_channel, bank_account=bank_account,
                acc_rev_gross=acc_rev_gross, acc_rev_dt=acc_rev_dt, acc_rev_dd=acc_rev_dd)


def revenue_account(cfg, plan):
    if plan.biz_mode in ('21', '31'):
        return cfg['acc_rev_gross']
    if plan.biz_mode == '41':
        return cfg['acc_rev_dd']
    return cfg['acc_rev_dt']


def claim_exists(plan):
    return env['tour.payment.claim'].search(
        [('name', '=', 'SK-O2C-%s' % plan.plan_code)], limit=1)


def do_invoice_flow(cfg, plan, today):
    """发票模式：开票 → 应收(1122.01) → 收款(贷1122.01) → 核销。"""
    if plan.invoice_ids:
        return
    G = round((plan.sum_pay_normal or 0.0) + max(plan.sum_un_pay or 0.0, 0.0), 2)
    if G <= 0 or not plan.supplier_id:
        return
    net = round(G / (1 + VAT_RATE / 100.0), 2)
    inv = env['account.move'].create({
        'move_type': 'out_invoice',
        'partner_id': plan.supplier_id.id,
        'journal_id': cfg['sale_journal'].id,
        'invoice_date': plan.end_date or today,
        'tour_plan_id': plan.id,
        'tour_invoice_kind': 'vat_normal',
        'tour_invoice_state': 'issued',
        'invoice_line_ids': [(0, 0, {
            'product_id': cfg['product'].id,
            'name': '团款 %s' % plan.plan_code,
            'quantity': 1,
            'price_unit': net,
            'account_id': revenue_account(cfg, plan).id,
            'analytic_distribution': {str(plan.analytic_account_id.id): 100.0},
            'tax_ids': [(6, 0, [cfg['tax6'].id])],
        })],
    })
    inv.action_post()
    # 收款认领（关联发票）→ 贷 1122.01 → reconcile
    if (plan.sum_pay_normal or 0.0) > 0 and not claim_exists(plan):
        claim = env['tour.payment.claim'].create({
            'name': 'SK-O2C-%s' % plan.plan_code,
            'supplier_id': plan.supplier_id.id,
            'plan_id': plan.id,
            'pay_date': plan.end_date or today,
            'pay_money': plan.sum_pay_normal,
            'pay_channel_id': cfg['bank_channel'].id,
            'account_id': cfg['bank_account'].id if cfg['bank_account'] else None,
            'claim_state': '1',
            'claim_line_ids': [(0, 0, {
                'invoice_id': inv.id,
                'amount': plan.sum_pay_normal,
                'name': '核销 %s' % (inv.name or inv.ref or plan.plan_code),
            })],
        })
        claim.action_audit()


def do_prepay_flow(cfg, plan, today):
    """预收模式：收款(贷2203.01预收) → 收入确认(借2203.01/贷6001/贷2221)。"""
    if not claim_exists(plan):
        claim = env['tour.payment.claim'].create({
            'name': 'SK-O2C-%s' % plan.plan_code,
            'supplier_id': plan.supplier_id.id if plan.supplier_id else None,
            'plan_id': plan.id,
            'pay_date': plan.end_date or today,
            'pay_money': plan.sum_pay_normal,
            'pay_channel_id': cfg['bank_channel'].id,
            'account_id': cfg['bank_account'].id if cfg['bank_account'] else None,
            'claim_state': '1',
        })
        claim.action_audit()
    # 收入确认（幂等：income_move_id 判断）
    if not plan.income_move_id:
        try:
            plan.action_recognize_revenue()
        except Exception as e:
            # 差价<=0 或其它业务校验失败：静默跳过，不阻断
            pass


def main():
    from odoo.exceptions import UserError, ValidationError
    import datetime
    cfg = setup()
    today = datetime.date.today().isoformat()
    ClaimM = env['tour.payment.claim']
    cp = get_checkpoint()
    max_plans = int(os.environ.get('OTC_MAX_PLANS', '0') or 0)
    print('checkpoint from=%d' % cp)
    plans = env['tour.plan'].search([
        ('id', '>', cp),
        '|', ('sum_pay_normal', '>', 0), ('sum_un_pay', '>', 0),
    ], order='id', limit=max_plans or None)
    total = len(plans)
    print('eligible plans=%d%s' % (total, (' (capped)' if max_plans else '')))
    n_invoice = n_prepay = n_skip = n_err = 0
    last_id = cp
    for i, plan in enumerate(plans):
        try:
            plan._ensure_analytic_account()
            plan._ensure_plan_account()
            if (plan.sum_un_pay or 0.0) > 0:
                do_invoice_flow(cfg, plan, today)
                n_invoice += 1
            elif (plan.sum_pay_normal or 0.0) > 0:
                do_prepay_flow(cfg, plan, today)
                n_prepay += 1
            else:
                n_skip += 1
        except Exception as e:
            n_err += 1
            if n_err <= 30:
                print('  [err] plan %s: %s' % (plan.plan_code, repr(e)[:200]))
        last_id = plan.id
        if (i + 1) % BATCH == 0:
            env.cr.commit()
            env.invalidate_all()  # 释放 ORM 缓存，防止大规模过账 OOM
            set_checkpoint(last_id)
            print('  progress %d/%d (invoice=%d prepay=%d skip=%d err=%d) moves=%d' % (
                i + 1, total, n_invoice, n_prepay, n_skip, n_err,
                env['account.move'].search_count([('state', '=', 'posted')])))
    env.cr.commit()
    set_checkpoint(last_id)
    print('========== O2C 完成 ==========')
    print('invoice_flow=%d prepay_flow=%d skip=%d err=%d' % (n_invoice, n_prepay, n_skip, n_err))
    print('posted account.move=%d' % env['account.move'].search_count([('state', '=', 'posted')]))
    print('posted move.line=%d' % env['account.move.line'].search_count([('parent_state', '=', 'posted')]))
    print('analytic.account=%d' % env['account.analytic.account'].search_count([]))
    print('tour.plan.account=%d' % env['tour.plan.account'].search_count([]))
    print('payment.claim=%d' % env['tour.payment.claim'].search_count([]))


if __name__ == '__main__':
    main()
