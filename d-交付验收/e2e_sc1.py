# -*- coding: utf-8 -*-
"""场景1：散客线上报名 → 成团 → 计调 → 收款 → 收入确认 → 成本 → 差额征税 → 分佣（真实数据贯通）

真实数据源：
  线路 663「三峡」(product.template list_price=225) / 班期 11631（published, 30 余位, 2026-10-29）
  真实客户档案 / 真实导游 6525 / 真实购物店 12197 / 真实银行日记账 BNK1
本脚本 commit 落库，供 psql 复核。
"""
import json
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
    if not a:
        return None
    env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line "
                   "WHERE account_id=%s AND parent_state='posted'", (a.id,))
    return round(env.cr.fetchone()[0] or 0.0, 2)


def move_lines(m):
    return [(l.account_id.code, round(l.debit, 2), round(l.credit, 2),
             l.analytic_distribution or {}, l.partner_id.name or '-') for l in m.line_ids]


def balanced(m):
    return round(sum(m.line_ids.mapped('debit')) - sum(m.line_ids.mapped('credit')), 2) == 0.0


def analytic_ok(m, aa):
    bad = [l.account_id.code for l in m.line_ids
           if str(aa.id) not in (l.analytic_distribution or {})]
    return bad


print('=== 场景1：线上报名 → 成团 → 计调 → 收款 → 收入确认 → 成本 → 分佣 ===')
Tag = 'UAT-E2E'
LINE = 663
DEP = 11631

# ---------- 快照 ----------
CODES = ['1002', '2203.01', '6001.01', '2221.01', '6401', '2202', '6401.07', '2241.02', '2221.05']
BEFORE = {c: bal(c) for c in CODES}
env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line WHERE parent_state='posted'")
GBAL0 = round(env.cr.fetchone()[0] or 0.0, 2)

# ---------- 步骤1 接单（线上官网报名） ----------
print('\n-- 步骤1 接单：线上官网报名 --')
line = env['tour.line'].browse(LINE)
dep = env['tour.departure'].browse(DEP)
print('  真实线路 %s / 班期 %s 余位=%s 价=%s' % (line.name, dep.name, dep.remain_seats, dep.get_online_prices()))
pre_plan = env['tour.plan'].search([('departure_id', '=', DEP)])
print('  该班期既有承载团: %s' % (pre_plan.mapped('plan_code') or '无'))

ADULT = 10
vals = {
    'supplier_name': '会泽海胤旅行社',          # 真实客户档案名（脱敏后仍为真实档案）
    'supplier_user_mobile': '13800138000',
    'supplier_user': '计调联系人',
    'adult_num': str(ADULT),
    'child_num': '0', 'old_man_num': '0', 'student_num': '0', 'baby_num': '0',
    'remark': '%s 场景1' % Tag,
}
passengers = [{'name': '客A%d' % i, 'passenger_type': 'adult', 'id_type': 'id_card',
               'id_number': '11010119900101%04d' % (1234 + i)} for i in range(1, ADULT + 1)]
reg = env['tour.plan.reg'].sudo().create_online_reg(line, dep, vals, passengers=passengers)
plan = reg.plan_id
QUOTE = round(ADULT * dep.get_online_prices()['adult'], 2)
check('1.1 报名落库', bool(reg), 'reg_code=%s id=%s' % (reg.reg_code, reg.id))
check('1.2 报名自动建团(draft)', plan.state == 'draft', 'plan=%s id=%s state=%s' % (plan.plan_code, plan.id, plan.state))
check('1.3 reg→plan/first_plan 回链', reg.plan_id.id == plan.id and reg.first_plan_id.id == plan.id,
      'plan_id=%s first_plan_id=%s' % (reg.plan_id.id, reg.first_plan_id.id))
check('1.4 报名金额=班期价×人数', abs(reg.in_com_quo_sum - QUOTE) < 0.01,
      'reg报价=%s 期望=%s' % (reg.in_com_quo_sum, QUOTE))
check('1.5 团金额汇总=Σ报名', abs(plan.in_com_quo_sum - QUOTE) < 0.01 and abs(plan.sum_un_pay - QUOTE) < 0.01,
      '团报价=%s 团未收=%s 期望=%s' % (plan.in_com_quo_sum, plan.sum_un_pay, QUOTE))
check('1.6 客人证件逐人落库', len(reg.passenger_ids) == ADULT, 'passengers=%d' % len(reg.passenger_ids))
check('1.7 余位回写', dep.remain_seats == 30 - ADULT, 'remain_seats=%s' % dep.remain_seats)
check('1.8 手机号加密+掩码', bool(reg.supplier_user_mobile_masked) and '13800138000' not in (reg.supplier_user_mobile or ''),
      '落盘=%s 掩码=%s' % (reg.supplier_user_mobile, reg.supplier_user_mobile_masked))

# 客户档案（真实 partner）：报名只写文本名，需人工挂档案
CUST = env['res.partner'].browse(9295)
plan.supplier_id = CUST.id
print('  挂客户档案: %s(id=%s)' % (CUST.name, CUST.id))

# ---------- 步骤2 成团 ----------
print('\n-- 步骤2 成团 --')
plan.action_confirm()
s1 = plan.state
plan.action_confirm()
s2 = plan.state
check('2.1 状态 draft→pending→confirmed', s1 == 'pending' and s2 == 'confirmed', '%s→%s' % (s1, s2))
check('2.2 成团自动建 analytic(单团核算)', bool(plan.analytic_account_id),
      'analytic=%s id=%s' % (plan.analytic_account_id.name, plan.analytic_account_id.id))
AA = plan.analytic_account_id
led = env['tour.plan.account'].search([('plan_id', '=', plan.id)])
check('2.3 成团自动建核算台账(1:1)', len(led) == 1, '台账=%s' % [(x.id, x.plan_code) for x in led])
check('2.4 analytic 1:1 绑定团', AA.tour_plan_id.id == plan.id, 'tour_plan_id=%s' % AA.tour_plan_id.id)

# ---------- 步骤3 计调 ----------
print('\n-- 步骤3 计调（派导/派车/订房/订餐/门票）--')
plan.action_operate()
check('3.1 状态 confirmed→operating', plan.state == 'operating', 'state=%s' % plan.state)
has_project_field = 'project_id' in plan._fields
has_task_model = 'project.task' in env
if not has_project_field or not has_task_model:
    gap('3.2 计调资源安排不可用', 'project_id 字段=%s / project.task 模型=%s（project、tour_operation 模块均为 uninstalled）'
        % (has_project_field, has_task_model))
else:
    check('3.2 计调 project 1:1 自动建', bool(plan.project_id))
    check('3.3 project 共享团 analytic', plan.project_id.account_id.id == AA.id)

# ---------- 步骤4 收款 ----------
print('\n-- 步骤4 收款（认领三步闭环）--')
ch = env['tour.pay.channel'].search([('channel_type', '=', 'bank_transfer')], limit=1)
bank_journal = env['account.journal'].browse(6)
claim = env['tour.payment.claim'].create({
    'supplier_id': CUST.id,
    'plan_id': plan.id,
    'pay_date': plan.begin_date,
    'pay_money': QUOTE,
    'pay_channel_id': ch.id,
    'account_id': bank_journal.id,
    'pay_way_id': env['tour.pay.way'].search([('name', '=', '公司现收')], limit=1).id,
    'brief': '%s 场景1 收款' % Tag,
})
check('4.1 收款登记落库(待认领)', claim.claim_state == '0', 'claim=%s id=%s' % (claim.name, claim.id))
claim.action_claim()
check('4.2 认领 0→1(待审核)', claim.claim_state == '1', 'claim_state=%s' % claim.claim_state)
try:
    claim.action_claim()
    gap('4.3 重复认领未拦截', '二次 action_claim 未抛错')
except ValidationError as e:
    check('4.3 重复认领被拦截', True, str(e)[:40])
claim.action_audit()
check('4.4 审核 1→2 + 生成收款凭证', claim.claim_state == '2' and bool(claim.move_id),
      'move=%s state=%s' % (claim.move_id.name, claim.move_id.state))
rc = claim.move_id
check('4.5 收款凭证借贷平衡', balanced(rc))
print('     收款凭证行: %s' % move_lines(rc))
check('4.6 借 1002 银行存款', any(
    l.account_id.code == '1002' and abs(l.debit - QUOTE) < 0.01 for l in rc.line_ids),
    '借1002=%s' % [l.debit for l in rc.line_ids if l.account_id.code == '1002'])
check('4.7 贷 2203.01 预收团款', any(l.account_id.code == '2203.01' and abs(l.credit - QUOTE) < 0.01 for l in rc.line_ids))
bad = analytic_ok(rc, AA)
check('4.8 收款凭证全行挂团 analytic', not bad, '未挂行=%s' % bad)
check('4.9 收款金额=报名金额=团金额', abs(claim.pay_money - reg.in_com_quo_sum) < 0.01 and abs(claim.pay_money - plan.in_com_quo_sum) < 0.01,
      'claim=%s reg=%s plan=%s' % (claim.pay_money, reg.in_com_quo_sum, plan.in_com_quo_sum))

# ---------- 步骤5 收入确认 ----------
print('\n-- 步骤5 出团/完成 → 收入确认 --')
plan.action_start()
check('5.1 状态 operating→in_progress', plan.state == 'in_progress', 'state=%s' % plan.state)
plan.action_complete()
check('5.2 状态 in_progress→completed', plan.state == 'completed', 'state=%s' % plan.state)
inc = plan.income_move_id
check('5.3 完成时自动生成收入凭证', bool(inc), 'move=%s state=%s' % (inc.name, inc.state))
NET = round(QUOTE / 1.06, 2)
TAX = round(QUOTE - NET, 2)
check('5.4 收入凭证借贷平衡', balanced(inc))
print('     收入凭证行: %s' % move_lines(inc))
d = [l for l in inc.line_ids if l.account_id.code == '2203.01']
c1 = [l for l in inc.line_ids if l.account_id.code == '6001.01']
c2 = [l for l in inc.line_ids if l.account_id.code == '2221.01']
check('5.5 借 2203.01 预收全额', bool(d) and abs(d[0].debit - QUOTE) < 0.01, 'debit=%s' % (d[0].debit if d else 0))
check('5.6 贷 6001.01 收入(不含税6%)', bool(c1) and abs(c1[0].credit - NET) < 0.01,
      'credit=%s 期望=%s' % (c1[0].credit if c1 else 0, NET))
check('5.7 贷 2221.01 销项税', bool(c2) and abs(c2[0].credit - TAX) < 0.01,
      'credit=%s 期望=%s' % (c2[0].credit if c2 else 0, TAX))
bad = analytic_ok(inc, AA)
check('5.8 收入凭证全行挂团 analytic', not bad, '未挂行=%s' % bad)

# ---------- 步骤6 成本（P2P） ----------
print('\n-- 步骤6 成本：供应商账单 → 请款 → 付款 --')
COST = 1500.0
plan.out_sum = COST   # 业务输入：线上报名路径不产生成本，成本须人工录入（见缺口）
print('  成本为业务输入（线上报名路径无成本来源）: out_sum=%s' % COST)
plan.action_generate_cost_bill()
bill = plan.cost_bill_id
check('6.1 生成成本应付账单', bool(bill), 'bill=%s state=%s type=%s' % (bill.name, bill.state, bill.move_type))
check('6.2 成本账单借贷平衡', balanced(bill))
print('     成本账单行: %s' % move_lines(bill))
d = [l for l in bill.line_ids if l.account_id.code == '6401']
c = [l for l in bill.line_ids if l.account_id.code == '2202']
check('6.3 借 6401 主营业务成本', bool(d) and abs(d[0].debit - COST) < 0.01, 'debit=%s' % (d[0].debit if d else 0))
check('6.4 贷 2202 应付账款', bool(c) and abs(c[0].credit - COST) < 0.01, 'credit=%s' % (c[0].credit if c else 0))
bad = analytic_ok(bill, AA)
if bad:
    gap('6.5 成本账单部分行未挂团 analytic', '未挂科目=%s（应付行按设计不挂团）' % bad)
else:
    check('6.5 成本账单全行挂团 analytic', True)
pr = env['tour.pay.request'].search([('bill_id', '=', bill.id)], limit=1)
check('6.6 自动生成请款单并审批', bool(pr) and pr.state == 'approved', 'request=%s state=%s' % (pr.name, pr.state))
print('  成本账单往来方(partner)=%s  ← plan.supplier_id 为客户档案' % bill.partner_id.name)
plan.action_pay_cost_bill()
check('6.7 付款核销应付(借2202/贷1002)', bill.payment_state == 'paid', 'payment_state=%s' % bill.payment_state)
pr2 = env['tour.pay.request'].search([('bill_id', '=', bill.id)], limit=1)
check('6.8 请款单联动已付款', pr2.state == 'paid', 'state=%s' % pr2.state)

# ---------- 步骤7 差额征税抵减 ----------
print('\n-- 步骤7 差额征税销项税额抵减 --')
try:
    plan.action_generate_vat_deduction()
    check('7.1 生成差额抵减凭证', bool(plan.vat_deduct_move_id),
          'move=%s' % (plan.vat_deduct_move_id.name if plan.vat_deduct_move_id else '-'))
except (ValidationError, UserError) as e:
    gap('7.1 差额征税抵减无法生成', str(e)[:110])
print('  可扣除成本基数: 可扣除=%s 发票缺口=%s' % (
    env['tour.plan.account']._plan_cost_vat_split(plan)[0], plan.un_invoice_money))

# ---------- 步骤8 分佣 ----------
print('\n-- 步骤8 分佣：计提 → 发放（含个税代扣）--')
guide = env['tour.guide'].browse(6525)
shop = env['res.partner'].browse(12197)
SHOP_AMT, RATE, SHARE = 20000.0, 10.0, 50.0
comm_total = round(SHOP_AMT * RATE / 100.0, 2)
before_tax = round(comm_total * SHARE / 100.0, 2)
print('  真实导游 %s / 真实购物店 %s；比例无数据来源（线路 guide_share_rate 全为 0、购物协议 0 条），按业务输入 10%%/50%%' % (guide.name, shop.name))
cm = env['tour.commission'].create({
    'plan_id': plan.id,
    'shop_id': shop.id,
    'shop_name': shop.name,
    'commission_rate': RATE,
    'shop_amount': SHOP_AMT,
    'commission_total': comm_total,
    'guide_id': guide.id,
    'guide_share_rate': SHARE,
    'guide_share_before_tax': before_tax,
})
check('8.1 佣金单落库(编号+员工回填)', bool(cm.name) and cm.name.startswith('YJ-') and bool(cm.employee_id),
      'name=%s 员工=%s 税务类型=%s' % (cm.name, cm.employee_id.name, cm.guide_tax_type))
EXP_TAX = round((before_tax - 800) * 0.20, 2) if before_tax <= 4000 else 0.0
check('8.2 劳务报酬个税预扣计算', abs(cm.guide_tax - EXP_TAX) < 0.01,
      '税前=%s 个税=%s 期望=%s 实发=%s' % (before_tax, cm.guide_tax, EXP_TAX, cm.guide_net_pay))
cm.action_confirm()
check('8.3 确认计提 + 生成计提凭证', cm.state == 'confirmed' and bool(cm.move_id),
      'move=%s' % cm.move_id.name)
acc = cm.move_id
check('8.4 计提凭证借贷平衡', balanced(acc))
print('     计提凭证行: %s' % move_lines(acc))
w1 = [l for l in acc.line_ids if l.account_id.code == '6401.07']
w2 = [l for l in acc.line_ids if l.account_id.code == '2241.02']
w3 = [l for l in acc.line_ids if l.account_id.code == '2221.05']
check('8.5 借 6401.07 导服成本=税前分成', bool(w1) and abs(w1[0].debit - before_tax) < 0.01, 'debit=%s' % (w1[0].debit if w1 else 0))
check('8.6 贷 2241.02 应付导游=实发', bool(w2) and abs(w2[0].credit - cm.guide_net_pay) < 0.01, 'credit=%s' % (w2[0].credit if w2 else 0))
check('8.7 贷 2221.05 代扣个税', bool(w3) and abs(w3[0].credit - cm.guide_tax) < 0.01, 'credit=%s' % (w3[0].credit if w3 else 0))
bad = analytic_ok(acc, AA)
check('8.8 计提凭证挂团 analytic', not bad, '未挂行=%s' % bad)
cm.action_receive()
check('8.9 佣金收款确认 confirmed→received', cm.state == 'received', 'state=%s' % cm.state)
cm.action_pay()
check('8.10 发放 + 生成发放凭证 paid', cm.state == 'paid' and bool(cm.pay_move_id), 'move=%s' % cm.pay_move_id.name)
pm = cm.pay_move_id
check('8.11 发放凭证借贷平衡', balanced(pm))
print('     发放凭证行: %s' % move_lines(pm))
check('8.12 借 2241.02 / 贷 1002 实发额', 
      any(l.account_id.code == '2241.02' and abs(l.debit - cm.guide_net_pay) < 0.01 for l in pm.line_ids)
      and any(l.account_id.code == '1002' and abs(l.credit - cm.guide_net_pay) < 0.01 for l in pm.line_ids))

# ---------- 步骤9 单团核算 ----------
print('\n-- 步骤9 单团核算（analytic 口径）--')
env.flush_all()
env.cr.execute("SELECT 1")
led.invalidate_recordset()
income_an, cost_an = env['tour.plan.account']._plan_analytic_balance(plan)
print('  analytic 口径: 收入=%s 成本=%s' % (income_an, cost_an))
check('9.1 单团收入(analytic)=不含税收入', abs(income_an - NET) < 0.01, 'analytic收入=%s 期望=%s(不含税)' % (income_an, NET))
check('9.2 单团成本(analytic)=成本账单+佣金', abs(cost_an - (COST + before_tax)) < 0.01,
      'analytic成本=%s 期望=%s' % (cost_an, COST + before_tax))
check('9.3 单团毛利=收入-成本', abs((led.profit) - (income_an - cost_an)) < 0.01,
      '台账毛利=%s 计算=%s' % (led.profit, income_an - cost_an))
check('9.4 台账 analytic = 团 analytic', led.analytic_account_id.id == AA.id, 'ledger=%s plan=%s' % (led.analytic_account_id.id, AA.id))
print('  口径说明: 业务报价(含税)=%s / 记账收入(不含税)=%s / 销项税=%s' % (QUOTE, NET, TAX))

# ---------- 步骤10 全库平衡 + 科目增量 ----------
print('\n-- 步骤10 借贷平衡与科目增量 --')
env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line WHERE parent_state='posted'")
GBAL1 = round(env.cr.fetchone()[0] or 0.0, 2)
check('10.1 全库凭证借贷平衡', abs(GBAL1) < 0.01, 'diff=%s' % GBAL1)
AFTER = {c: bal(c) for c in CODES}
delta = {c: round((AFTER[c] or 0) - (BEFORE[c] or 0), 2) for c in CODES}
print('  科目增量: %s' % json.dumps(delta, ensure_ascii=False))
check('10.2 1002 银行存款 Δ=收款-付款', abs(delta['1002'] - (QUOTE - COST - cm.guide_net_pay)) < 0.01,
      'Δ=%s 期望=%s' % (delta['1002'], QUOTE - COST - cm.guide_net_pay))
check('10.3 2203.01 预收结转结平', abs(delta['2203.01']) < 0.01, 'Δ=%s' % delta['2203.01'])
check('10.4 6001.01 收入(不含税)', abs(delta['6001.01'] + NET) < 0.01, 'Δ=%s 期望=-%s' % (delta['6001.01'], NET))
check('10.5 2221.01 销项税', abs(delta['2221.01'] + TAX) < 0.01, 'Δ=%s 期望=-%s' % (delta['2221.01'], TAX))
check('10.6 6401 成本', abs(delta['6401'] - COST) < 0.01, 'Δ=%s 期望=%s' % (delta['6401'], COST))
check('10.7 6401.07 导服成本', abs(delta['6401.07'] - before_tax) < 0.01, 'Δ=%s 期望=%s' % (delta['6401.07'], before_tax))
check('10.8 2202 应付结平', abs(delta['2202']) < 0.01, 'Δ=%s' % delta['2202'])
check('10.9 2241.02 应付导游结平', abs(delta['2241.02']) < 0.01, 'Δ=%s' % delta['2241.02'])
check('10.10 2221.05 个税负债', abs(delta['2221.05'] + cm.guide_tax) < 0.01, 'Δ=%s 期望=-%s' % (delta['2221.05'], cm.guide_tax))

print('\n########## 场景1 汇总 ##########')
print('plan_id=%s plan_code=%s reg_id=%s claim_id=%s bill=%s income_move=%s commission=%s analytic=%s' % (
    plan.id, plan.plan_code, reg.id, claim.id, bill.name, inc.name, cm.name, AA.id))
print('PASS=%d FAIL=%d GAP=%d' % (len(PASS), len(FAIL), len(GAP)))
if FAIL:
    print('FAIL: %s' % FAIL)
if GAP:
    print('GAP: %s' % GAP)

env.cr.commit()
print('[COMMITTED]')
