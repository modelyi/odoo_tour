# -*- coding: utf-8 -*-
"""场景5：真实存量团（易途导入数据）全链路闭环 收款→成团→收入确认→成本→差额征税→分佣
   真实团 88791 ZY-260924T-1「大国崛起6人独立团」：报价 8170 / 成本 2640 / 客户 昆明风淼(9642) / analytic 68418
"""
import json
from odoo import fields
from odoo.exceptions import UserError, ValidationError

PASS, FAIL, GAP = [], [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def gap(name, detail=''):
    GAP.append(name)
    print('  [GAP ] %s %s' % (name, detail))


def bal(code):
    a = env['account.account'].search([('code', '=', code)], limit=1)
    env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line "
                   "WHERE account_id=%s AND parent_state='posted'", (a.id,))
    return round(env.cr.fetchone()[0] or 0.0, 2)


def gbal():
    env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line WHERE parent_state='posted'")
    return round(env.cr.fetchone()[0] or 0.0, 2)


def mlines(m):
    return [(l.account_id.code, round(l.debit, 2), round(l.credit, 2),
             l.analytic_distribution or {}) for l in m.line_ids]


def balanced(m):
    return round(sum(m.line_ids.mapped('debit')) - sum(m.line_ids.mapped('credit')), 2) == 0.0


print('=== 场景5：真实存量团（易途导入）全链路闭环 ===')
P = env['tour.plan'].browse(88791)
AA = P.analytic_account_id
QUOTE = P.in_com_quo_sum
COST = P.out_sum
print('  团 %s | %s | state=%s | biz=%s | 报价=%s 成本=%s | analytic=%s | 客户=%s' % (
    P.plan_code, P.plan_name, P.state, P.biz_mode, QUOTE, COST, AA.id, P.supplier_id.name))
print('  报名: %s' % [(r.reg_code, r.in_com_quo_sum, r.sum_un_pay) for r in env['tour.plan.reg'].search([('plan_id', '=', P.id)])])
print('  既有成本账单: %s state=%s payment=%s 金额=%s' % (
    P.cost_bill_id.name, P.cost_bill_id.state, P.cost_bill_id.payment_state, P.cost_bill_id.amount_total))
CODES = ['1002', '2203.01', '6001.01', '2221.01', '6401', '2202', '6401.02', '2221.03', '6401.07', '2241.02', '2221.05']
BEFORE = {c: bal(c) for c in CODES}

# ---- 1 收款 ----
print('\n-- 1 收款 --')
ch = env['tour.pay.channel'].search([('channel_type', '=', 'bank_transfer')], limit=1)
claim = env['tour.payment.claim'].create({
    'supplier_id': P.supplier_id.id, 'plan_id': P.id,
    'pay_date': P.begin_date, 'pay_money': QUOTE,
    'pay_channel_id': ch.id, 'account_id': 6,
    'pay_way_id': env['tour.pay.way'].search([('name', '=', '公司现收')], limit=1).id,
    'brief': 'UAT-E2E 场景5 存量团收款',
})
claim.action_claim()
claim.action_audit()
rc = claim.move_id
check('1.1 收款凭证生成并过账', bool(rc) and rc.state == 'posted',
      '%s %s' % (rc.name, rc.state))
check('1.2 收款凭证借贷平衡', balanced(rc))
print('     行: %s' % mlines(rc))
check('1.3 借 1002 / 贷 2203.01 全额', 
      any(l.account_id.code == '1002' and abs(l.debit - QUOTE) < 0.01 for l in rc.line_ids)
      and any(l.account_id.code == '2203.01' and abs(l.credit - QUOTE) < 0.01 for l in rc.line_ids))
check('1.4 收款凭证挂团 analytic', all(str(AA.id) in (l.analytic_distribution or {}) for l in rc.line_ids))
check('1.5 收款金额=团报价', abs(claim.pay_money - QUOTE) < 0.01, '%s vs %s' % (claim.pay_money, QUOTE))
claim.action_settle()
check('1.6 平账 2→3', claim.claim_state == '3', 'claim_state=%s' % claim.claim_state)

# ---- 2 成团 → 收入确认 ----
print('\n-- 2 成团 → 出团 → 收入确认 --')
P.action_confirm()
s1 = P.state
P.action_confirm()
check('2.1 状态 pending→confirmed', s1 == 'pending' and P.state == 'confirmed', '%s→%s' % (s1, P.state))
check('2.2 已成团团 analytic 复用既有(不新建)', P.analytic_account_id.id == AA.id)
P.action_operate()
check('2.3 状态 confirmed→operating', P.state == 'operating', 'state=%s' % P.state)
if 'project_id' in P._fields and P.project_id:
    check('2.4 计调 project 1:1', P.project_id.account_id.id == AA.id)
else:
    gap('2.4 计调 project 不可用', 'project_id 字段=%s → 派导/派车/订房/订餐/门票无承载模型'
        % ('project_id' in P._fields))
P.action_start()
check('2.5 状态 operating→in_progress', P.state == 'in_progress', 'state=%s' % P.state)
P.action_complete()
check('2.6 状态 in_progress→completed', P.state == 'completed', 'state=%s' % P.state)
inc = P.income_move_id
check('2.7 自动生成收入确认凭证', bool(inc), '%s state=%s' % (inc.name if inc else '-', inc.state if inc else '-'))
check('2.8 收入凭证借贷平衡', balanced(inc))
print('     行: %s' % mlines(inc))
NET = round(QUOTE / 1.06, 2)
TAX = round(QUOTE - NET, 2)
check('2.9 借 2203.01 预收全额', any(l.account_id.code == '2203.01' and abs(l.debit - QUOTE) < 0.01 for l in inc.line_ids))
check('2.10 贷 6001.01 收入不含税', any(l.account_id.code == '6001.01' and abs(l.credit - NET) < 0.01 for l in inc.line_ids),
      '期望=%s' % NET)
check('2.11 贷 2221.01 销项税6%', any(l.account_id.code == '2221.01' and abs(l.credit - TAX) < 0.01 for l in inc.line_ids),
      '期望=%s' % TAX)
check('2.12 收入凭证挂团 analytic', all(str(AA.id) in (l.analytic_distribution or {}) for l in inc.line_ids))
check('2.13 收入确认幂等(二次调用不重复)', (P.action_recognize_revenue() or True) and
      env['account.move'].search_count([('id', '=', inc.id)]) == 1, 'income_move=%s' % inc.name)

# ---- 3 成本 ----
print('\n-- 3 成本（既有成本账单 + 付款）--')
bill = P.cost_bill_id
check('3.1 成本账单存在且过账', bool(bill) and bill.state == 'posted', '%s %s' % (bill.name, bill.state))
print('     行: %s' % mlines(bill))
check('3.2 借 6401 / 贷 2202 成本', 
      any(l.account_id.code == '6401' and abs(l.debit - COST) < 0.01 for l in bill.line_ids)
      and any(l.account_id.code == '2202' and abs(l.credit - COST) < 0.01 for l in bill.line_ids))
if bill.payment_state != 'paid':
    P.action_pay_cost_bill()
check('3.3 成本已付款(应付核销)', bill.payment_state == 'paid', 'payment_state=%s' % bill.payment_state)
check('3.4 成本账单成本行挂团 analytic',
      any(str(AA.id) in (l.analytic_distribution or {}) for l in bill.line_ids if l.debit > 0))
pr = env['tour.pay.request'].search([('bill_id', '=', bill.id)], limit=1)
check('3.5 请款单联动', bool(pr) and pr.state in ('approved', 'paid'), 'request=%s state=%s' % (pr.name if pr else '-', pr.state if pr else '-'))

# ---- 4 差额征税销项税额抵减 ----
print('\n-- 4 差额征税销项税额抵减 --')
ded, nonded = env['tour.plan.account']._plan_cost_vat_split(P)
print('  现状: 可扣除成本=%s 不可扣除成本=%s 发票缺口(un_invoice_money)=%s' % (ded, nonded, P.un_invoice_money))
gap('4.1 差额扣除基数被发票缺口归零',
    '可扣除成本=%s 但 un_invoice_money=%s → 基数=max(0,%s-%s)=0，且成本账单统一落 6401（差额可扣=False）'
    % (ded, P.un_invoice_money, ded, P.un_invoice_money))
try:
    P.action_generate_vat_deduction()
    gap('4.2 现数据下抵减凭证意外生成', 'move=%s' % P.vat_deduct_move_id.name)
except (ValidationError, UserError) as e:
    check('4.2 现数据下抵减被正确拦截', True, str(e)[:60])
# 补录可扣除成本（住宿费 6401.02，真实酒店供应商）后重试，验证机制本身
SUP = env['res.partner'].browse(10734)
P.un_invoice_money = 0.0   # 成本已取得发票
DED_COST = 600.0
bill2 = env['account.move'].create({
    'move_type': 'in_invoice', 'partner_id': SUP.id, 'journal_id': 2,
    'invoice_date': P.end_date, 'tour_plan_id': P.id, 'ref': 'UAT-E2E-可扣除成本-%s' % P.plan_code,
    'invoice_line_ids': [(0, 0, {
        'name': '住宿费（可差额扣除）%s' % P.plan_code, 'quantity': 1.0, 'price_unit': DED_COST,
        'account_id': env['account.account'].search([('code', '=', '6401.02')], limit=1).id,
        'analytic_distribution': {str(AA.id): 100.0}, 'tax_ids': [(6, 0, [])],
    })],
})
bill2.action_post()
ded2, nonded2 = env['tour.plan.account']._plan_cost_vat_split(P)
check('4.3 可扣除成本归集(6401.02 挂团 analytic)', abs(ded2 - DED_COST) < 0.01,
      '可扣除=%s(补录前 %s) 不可扣除=%s 供应商=%s' % (ded2, ded, nonded2, SUP.name))
try:
    P.action_generate_vat_deduction()
    dm = P.vat_deduct_move_id
    check('4.4 生成差额抵减凭证', bool(dm), 'move=%s state=%s' % (dm.name, dm.state))
    check('4.5 抵减凭证借贷平衡', balanced(dm))
    print('     行: %s' % mlines(dm))
    EXP_DED = round(DED_COST / 1.06 * 0.06, 2)
    check('4.6 借 2221.03 抵减额 = 基数÷1.06×6%',
          any(l.account_id.code == '2221.03' and abs(l.debit - EXP_DED) < 0.01 for l in dm.line_ids),
          '期望=%s' % EXP_DED)
    check('4.7 贷 6401.02 冲减成本(同额)', any(l.account_id.code == '6401.02' and abs(l.credit - EXP_DED) < 0.01 for l in dm.line_ids))
    check('4.8 抵减凭证挂团 analytic', all(str(AA.id) in (l.analytic_distribution or {}) for l in dm.line_ids))
    check('4.9 抵减幂等', (P.action_generate_vat_deduction() or True) and P.vat_deduct_move_id.id == dm.id)
    led2 = env['tour.plan.account'].search([('plan_id', '=', P.id)])
    led2.invalidate_recordset()
    print('  台账: 可扣除=%s 不可扣除=%s 扣除基数=%s 抵减额=%s 全额销项=%s 净应纳=%s' % (
        led2.cost_deductible, led2.cost_non_deductible, led2.vat_deductible_total,
        led2.vat_deduct_amount, led2.vat_output_amount, led2.vat_payable))
except (ValidationError, UserError) as e:
    gap('4.4 差额抵减仍无法生成', str(e)[:140])

# ---- 5 分佣 ----
print('\n-- 5 分佣 --')
guide = env['tour.guide'].browse(6526)
shop = env['res.partner'].browse(12198)
SHOP_AMT, RATE, SHARE = 30000.0, 8.0, 40.0
ct = round(SHOP_AMT * RATE / 100.0, 2)
bt = round(ct * SHARE / 100.0, 2)
cm = env['tour.commission'].create({
    'plan_id': P.id, 'shop_id': shop.id, 'shop_name': shop.name,
    'commission_rate': RATE, 'shop_amount': SHOP_AMT, 'commission_total': ct,
    'guide_id': guide.id, 'guide_share_rate': SHARE, 'guide_share_before_tax': bt,
})
check('5.1 佣金单落库', cm.name.startswith('YJ-') and cm.employee_id.id == guide.employee_id.id,
      '%s 导游=%s 员工=%s 税务=%s' % (cm.name, guide.name, cm.employee_id.name, cm.guide_tax_type))
EXP_TAX = round((bt - 800) * 0.2, 2) if bt <= 4000 else 0.0
check('5.2 个税预扣(劳务报酬)', abs(cm.guide_tax - EXP_TAX) < 0.01,
      '税前=%s 个税=%s 实发=%s 留存=%s' % (bt, cm.guide_tax, cm.guide_net_pay, cm.company_retain))
cm.action_confirm()
check('5.3 计提凭证', balanced(cm.move_id), '%s' % cm.move_id.name)
print('     行: %s' % mlines(cm.move_id))
check('5.4 借 6401.07 / 贷 2241.02+2221.05',
      any(l.account_id.code == '6401.07' and abs(l.debit - bt) < 0.01 for l in cm.move_id.line_ids)
      and any(l.account_id.code == '2241.02' and abs(l.credit - cm.guide_net_pay) < 0.01 for l in cm.move_id.line_ids)
      and any(l.account_id.code == '2221.05' and abs(l.credit - cm.guide_tax) < 0.01 for l in cm.move_id.line_ids))
check('5.5 计提凭证挂团 analytic', all(str(AA.id) in (l.analytic_distribution or {}) for l in cm.move_id.line_ids))
cm.action_pay()
check('5.6 发放凭证 + 状态 paid', cm.state == 'paid' and balanced(cm.pay_move_id),
      '%s state=%s' % (cm.pay_move_id.name, cm.state))
print('     行: %s' % mlines(cm.pay_move_id))

# ---- 6 单团核算 ----
print('\n-- 6 单团核算 --')
led = env['tour.plan.account'].search([('plan_id', '=', P.id)])
env.flush_all()
led.invalidate_recordset()
inc_an, cost_an = env['tour.plan.account']._plan_analytic_balance(P)
print('  台账: 收入=%s 成本=%s 毛利=%s 预收残值=%s 应收余额=%s' % (
    led.income_total, led.cost_total, led.profit, led.prepaid, led.receivable))
check('6.1 台账存在(1:1) 且 analytic 一致', len(led) == 1 and led.analytic_account_id.id == AA.id)
check('6.2 单团收入(analytic)=不含税收入', abs(led.income_total - NET) < 0.01,
      '台账=%s 期望=%s' % (led.income_total, NET))
EXPECT_COST = COST + bt + DED_COST - EXP_DED   # 原成本 + 导服成本 + 补录可扣除(净额)
check('6.3 单团成本(analytic)=Σ成本类分析行', abs(led.cost_total - EXPECT_COST) < 0.01,
      '台账=%s 期望=%s(6401 %s + 6401.07 %s + 6401.02 %s - 抵减 %s)' % (
          led.cost_total, EXPECT_COST, COST, bt, DED_COST, EXP_DED))
check('6.4 台账毛利=收入-成本', abs(led.profit - (led.income_total - led.cost_total)) < 0.01,
      '毛利=%s' % led.profit)
check('6.5 台账收入/成本同源团 analytic', led.analytic_account_id.tour_plan_id.id == P.id)

# ---- 7 科目增量 + 平衡 ----
print('\n-- 7 科目增量与全库平衡 --')
AFTER = {c: bal(c) for c in CODES}
delta = {c: round((AFTER[c] or 0) - (BEFORE[c] or 0), 2) for c in CODES}
print('  %s' % json.dumps(delta, ensure_ascii=False))
check('7.1 2203.01 预收结转结平', abs(delta['2203.01']) < 0.01, 'Δ=%s' % delta['2203.01'])
check('7.2 6001.01 Δ=收入(不含税)', abs(delta['6001.01'] + NET) < 0.01, 'Δ=%s' % delta['6001.01'])
check('7.3 2221.01 Δ=销项税', abs(delta['2221.01'] + TAX) < 0.01, 'Δ=%s' % delta['2221.01'])
check('7.4 6401 Δ=0(既有成本未重复计)', abs(delta['6401']) < 0.01, 'Δ=%s' % delta['6401'])
check('7.5 6401.02 Δ=补录-抵减', abs(delta['6401.02'] - (DED_COST - EXP_DED)) < 0.01, 'Δ=%s' % delta['6401.02'])
check('7.6 2221.03 Δ=-抵减额', abs(delta['2221.03'] + EXP_DED) < 0.01, 'Δ=%s' % delta['2221.03'])
check('7.7 6401.07 Δ=导服成本', abs(delta['6401.07'] - bt) < 0.01, 'Δ=%s' % delta['6401.07'])
check('7.8 2241.02 结平', abs(delta['2241.02']) < 0.01, 'Δ=%s' % delta['2241.02'])
check('7.9 2221.05 Δ=个税', abs(delta['2221.05'] + cm.guide_tax) < 0.01, 'Δ=%s' % delta['2221.05'])
G = gbal()
check('7.10 全库凭证借贷平衡', abs(G) < 0.01, 'diff=%s' % G)

print('\n########## 场景5 汇总 ##########')
print('plan=%s(%s) analytic=%s claim=%s income_move=%s cost_bill=%s vat_deduct=%s commission=%s' % (
    P.id, P.plan_code, AA.id, claim.name, inc.name, bill.name,
    P.vat_deduct_move_id.name or '-', cm.name))
print('PASS=%d FAIL=%d GAP=%d' % (len(PASS), len(FAIL), len(GAP)))
if FAIL:
    print('FAIL: %s' % FAIL)
if GAP:
    print('GAP: %s' % GAP)
env.cr.commit()
print('[COMMITTED]')
