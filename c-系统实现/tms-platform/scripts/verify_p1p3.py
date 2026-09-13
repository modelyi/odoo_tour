# -*- coding: utf-8 -*-
"""P1 + P3 UAT 修复验证（odoo shell 单事务实测，末尾 rollback 零残留）。"""
import traceback

Plan = env['tour.plan']
Move = env['account.move']
Acc = env['account.account']
PAcc = env['tour.plan.account']
Company = env.company

results = []

def check(name, actual, expected, tol=0.02):
    ok = abs((actual or 0.0) - expected) <= tol
    results.append((name, ok, actual, expected))
    print(('PASS' if ok else 'FAIL'), '|', name, '=', round(actual or 0.0, 4), '(期望', expected, ')')
    return ok

def get_acc(code):
    a = Acc.search([('code', '=', code)], limit=1)
    if not a:
        raise RuntimeError('account not found: ' + code)
    return a

line = env['tour.line'].search([], limit=1)
assert line, 'no tour.line found'

orig = (Company.tour_taxpayer_type, Company.tour_vat_rate,
        Company.tour_vat_levy_rate, Company.tour_diff_tax_enabled)

def set_company(tp, rate, levy, enabled):
    Company.write({'tour_taxpayer_type': tp, 'tour_vat_rate': rate,
                   'tour_vat_levy_rate': levy, 'tour_diff_tax_enabled': enabled})

def make_plan(code, biz_mode, in_sum=0.0, out_sum=0.0):
    p = Plan.create({
        'plan_code': code, 'plan_name': code,
        'line_id': line.id,
        'begin_date': '2026-09-01', 'end_date': '2026-09-03',
        'guest_count': 1, 'biz_mode': biz_mode,
        'in_sum': in_sum, 'out_sum': out_sum,
    })
    p.action_confirm()
    p.action_confirm()
    return p

def post_move(plan, lines, journal_type='general', ref='T'):
    j = plan._tour_get_journal(journal_type)
    mv = plan._tour_make_move(j, '2026-09-13', ref, lines)
    mv.action_post()
    return mv

try:
    # ============ 示例A：一般纳税人 6% 总额法（P1 主回归）============
    set_company('general', 6.0, 3.0, True)
    pA = make_plan('UAT-P1-A', '21')
    analytic = pA._plan_analytic_distribution(pA)
    cost_acc = get_acc('6401.01')      # 可扣除（地接）
    nonded_acc = get_acc('6401.07')    # 不可扣除（导服）
    prepay = get_acc('2203.01')
    rev = get_acc('6001.01')
    out_tax = get_acc('2221.01')
    deduct_acc = get_acc('2221.03')
    bank = get_acc('1002')

    # D=63600 可扣除 + N=10600 不可扣除
    post_move(pA, [
        {'account_id': cost_acc.id, 'debit': 63600.0, 'analytic': analytic, 'name': '地接成本'},
        {'account_id': bank.id, 'credit': 63600.0, 'analytic': analytic, 'name': '支付'},
    ])
    post_move(pA, [
        {'account_id': nonded_acc.id, 'debit': 10600.0, 'analytic': analytic, 'name': '导服成本'},
        {'account_id': bank.id, 'credit': 10600.0, 'analytic': analytic, 'name': '支付'},
    ])
    # G=106000 含税 → 收入 100000 + 销项 6000
    post_move(pA, [
        {'account_id': prepay.id, 'debit': 106000.0, 'analytic': analytic, 'name': '结转预收'},
        {'account_id': rev.id, 'credit': 100000.0, 'analytic': analytic, 'name': '收入不含税'},
        {'account_id': out_tax.id, 'credit': 6000.0, 'analytic': analytic, 'name': '销项税'},
    ])

    mvA = Move.browse(pA._generate_vat_deduction_move())
    dl = mvA.line_ids.filtered(lambda l: l.account_id.id == deduct_acc.id)
    cl = mvA.line_ids.filtered(lambda l: l.account_id.id == cost_acc.id)
    check('示例A 抵减凭证借方2221.03', sum(dl.mapped('debit')), 3600.0)
    check('示例A 抵减凭证贷方6401.01', sum(cl.mapped('credit')), 3600.0)

    # 直接验证根因方法：只汇总借方，贷方抵减行不计入
    ded, non_ded = pA._plan_cost_vat_split(pA)
    check('示例A _plan_cost_vat_split 可扣除', ded, 63600.0)
    check('示例A _plan_cost_vat_split 不可扣除', non_ded, 10600.0)

    paA = PAcc.search([('plan_id', '=', pA.id)], limit=1)
    check('示例A 台账 income_total', paA.income_total, 100000.0)
    check('示例A 台账 cost_total(净)', paA.cost_total, 70600.0)
    check('示例A 台账 cost_deductible', paA.cost_deductible, 63600.0)
    check('示例A 台账 vat_deductible_total', paA.vat_deductible_total, 63600.0)
    check('示例A 台账 vat_deduct_amount', paA.vat_deduct_amount, 3600.0)
    check('示例A 台账 vat_output_amount', paA.vat_output_amount, 6000.0)
    check('示例A 台账 vat_payable', paA.vat_payable, 2400.0)

    # ============ 示例B：小规模 3% 净应交 1500 ============
    set_company('small', 6.0, 3.0, True)
    pB = make_plan('UAT-P1-B', '21')
    analyticB = pB._plan_analytic_distribution(pB)
    simple_tax = get_acc('2221.07')
    # D=51500, G=103000 → 收入 100000 + 简易税 3000
    post_move(pB, [
        {'account_id': cost_acc.id, 'debit': 51500.0, 'analytic': analyticB, 'name': '可扣除成本'},
        {'account_id': bank.id, 'credit': 51500.0, 'analytic': analyticB, 'name': '支付'},
    ])
    post_move(pB, [
        {'account_id': prepay.id, 'debit': 103000.0, 'analytic': analyticB, 'name': '结转预收'},
        {'account_id': rev.id, 'credit': 100000.0, 'analytic': analyticB, 'name': '收入不含税'},
        {'account_id': simple_tax.id, 'credit': 3000.0, 'analytic': analyticB, 'name': '简易计税'},
    ])
    mvB = Move.browse(pB._generate_vat_deduction_move())
    check('示例B 抵减凭证贷方6401.01', sum(mvB.line_ids.filtered(
        lambda l: l.account_id.id == cost_acc.id).mapped('credit')), 1500.0)
    paB = PAcc.search([('plan_id', '=', pB.id)], limit=1)
    check('示例B 台账 vat_deduct_amount', paB.vat_deduct_amount, 1500.0)
    check('示例B 台账 vat_payable', paB.vat_payable, 1500.0)

    # ============ 示例C：净额法 差价 339.62 ============
    set_company('general', 6.0, 3.0, True)
    pC = make_plan('UAT-P1-C', '1', in_sum=106000.0, out_sum=100000.0)
    check('示例C 差价 _revenue_amount', pC._revenue_amount(), 6000.0)
    analyticC = pC._plan_analytic_distribution(pC)
    mvC = Move.browse(pC._generate_revenue_move())
    net_rev_line = mvC.line_ids.filtered(lambda l: l.account_id.id == get_acc('6001.02').id)
    tax_line = mvC.line_ids.filtered(lambda l: l.account_id.id == out_tax.id)
    check('示例C 收入(不含税) 6001.02', sum(net_rev_line.mapped('credit')), 5660.38)
    check('示例C 销项税 2221.01', sum(tax_line.mapped('credit')), 339.62)

    # ============ P3-1：action_audit 重复调用 ============
    set_company('general', 6.0, 3.0, True)
    pD = make_plan('UAT-P3-1', '21')
    channel = env['tour.pay.channel'].search([('channel_type', '=', 'cash')], limit=1)
    assert channel, 'no cash channel'
    cust = env['res.partner'].search([('sup_type', '=', 'customer')], limit=1)
    Claim = env['tour.payment.claim']
    cl = Claim.create({
        'plan_id': pD.id, 'supplier_id': cust.id if cust else False,
        'pay_date': '2026-09-12', 'pay_money': 5000.0,
        'pay_channel_id': channel.id,
    })
    cl.action_claim()
    first_move = None
    raised = False
    try:
        cl.action_audit()
        first_move = cl.move_id
        # 二次调用：不应抛错、不应重复生成凭证
        cl.action_audit()
    except Exception as e:
        raised = True
        print('P3-1 action_audit 二次调用抛错:', repr(e))
    check('P3-1 action_audit 二次调用不抛错', 1.0 if not raised else 0.0, 1.0)
    check('P3-1 凭证不重复(move_id 不变)', cl.move_id.id, first_move.id)
    check('P3-1 状态=已审核', 1.0 if cl.claim_state == '2' else 0.0, 1.0)

    # ============ P3-2：佣金计提/发放 个税行 analytic ============
    set_company('general', 6.0, 3.0, True)
    pE = make_plan('UAT-P3-2', '21')
    guide = env['tour.guide'].search([('audit_chk', '=', True)], limit=1)
    cm = env['tour.commission'].create({
        'plan_id': pE.id,
        'guide_id': guide.id if guide else False,
        'commission_total': 3000.0,
        'guide_share_before_tax': 1500.0,
        'premium': 0.0,
        'guide_tax_type': 'labor',
    })
    cm.action_confirm()
    accA = cm.move_id
    aa_id = pE.analytic_account_id.id
    tax_ln = accA.line_ids.filtered(lambda l: l.account_id.id == get_acc('2221.05').id)
    tax_analytic = tax_ln.analytic_distribution or {}
    check('P3-2 计提个税行有 analytic',
          1.0 if str(aa_id) in tax_analytic else 0.0, 1.0)
    cm.action_pay()
    pay_lines = cm.pay_move_id.line_ids
    pay_analytic_ok = all(
        (str(aa_id) in (l.analytic_distribution or {})) for l in pay_lines)
    check('P3-2 发放凭证两行均有 analytic', 1.0 if pay_analytic_ok else 0.0, 1.0)

    print('\n===== 结果汇总 =====')
    passed = sum(1 for r in results if r[1])
    print('通过 %d / %d' % (passed, len(results)))
    for r in results:
        if not r[1]:
            print('  FAIL:', r[0], '实际', r[2], '期望', r[3])

finally:
    # 恢复公司配置并回滚整笔事务，零残留
    try:
        Company.write({'tour_taxpayer_type': orig[0], 'tour_vat_rate': orig[1],
                       'tour_vat_levy_rate': orig[2], 'tour_diff_tax_enabled': orig[3]})
    except Exception:
        pass
    env.cr.rollback()
    print('\n[已回滚，无测试数据残留]')
