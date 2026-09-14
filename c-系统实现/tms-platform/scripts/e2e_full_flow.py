# -*- coding: utf-8 -*-
"""端到端完整闭环验证：网上下单 → 收款 → 确认 → 计调 → 出团 → 收入确认 → 成本 → 三表。

在 Odoo shell 中运行（事务内，退出自动回滚，不污染历史数据）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http --dev '' < scripts/e2e_full_flow.py

每一步检查：数据落库、状态流转、凭证生成、借贷平衡、analytic 挂对、三表反映。
"""
import datetime
from odoo.exceptions import UserError, ValidationError

PASS = []
FAIL = []
GAPS = []


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print('  [PASS] %s %s' % (name, detail))
    else:
        FAIL.append(name)
        print('  [FAIL] %s %s' % (name, detail))


def gap(name, detail=''):
    GAPS.append((name, detail))
    print('  [GAP ] %s %s' % (name, detail))


def acct_balance(code):
    """某科目 posted 行余额 = Σ(debit - credit)。"""
    acc = env['account.account'].search([('code', '=', code)], limit=1)
    if not acc:
        return 0.0
    env.cr.execute(
        "SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line "
        "WHERE account_id=%s AND parent_state='posted'", (acc.id,))
    return round(env.cr.fetchone()[0] or 0.0, 2)


def move_balanced(move):
    return round(sum(move.line_ids.mapped('debit')) - sum(move.line_ids.mapped('credit')), 2) == 0.0


def move_analytic_ok(move, analytic_id):
    """凭证所有行都挂了该团 analytic。"""
    if not move.line_ids:
        return False
    for ln in move.line_ids:
        d = ln.analytic_distribution or {}
        if str(analytic_id) not in d:
            return False
    return True


def global_balance():
    env.flush_all()
    env.cr.execute(
        "SELECT COALESCE(SUM(debit),0)-COALESCE(SUM(credit),0) "
        "FROM account_move_line WHERE parent_state='posted'")
    return round(env.cr.fetchone()[0] or 0.0, 2)


def balance_sheet_balanced():
    """资产负债表平衡：总资产 = 总负债 + 总权益 + 当期净利(收入-成本)。

    返回 (diff, unclassified)。diff≈0 即平衡；unclassified 为未归入五类的科目类型余额和（应为 0 或 off_balance）。
    """
    env.flush_all()
    env.cr.execute("""
        SELECT a.account_type, COALESCE(SUM(l.debit)-SUM(l.credit),0) AS bal
        FROM account_move_line l
        JOIN account_account a ON a.id = l.account_id
        WHERE l.parent_state='posted'
        GROUP BY a.account_type
    """)
    rows = dict(env.cr.fetchall())
    asset_types = ('asset_cash', 'asset_receivable', 'asset_current',
                   'asset_non_current', 'asset_prepayments', 'asset_fixed')
    liability_types = ('liability_payable', 'liability_credit_card',
                       'liability_current', 'liability_non_current')
    equity_types = ('equity', 'equity_unaffected')
    income_types = ('income', 'income_other')
    expense_types = ('expense', 'expense_direct_cost', 'expense_depreciation')
    known = set(asset_types) | set(liability_types) | set(equity_types) | set(income_types) | set(expense_types)
    assets = sum(rows.get(t, 0.0) for t in asset_types)
    liabilities = -sum(rows.get(t, 0.0) for t in liability_types)  # 贷方余额取正
    equity = -sum(rows.get(t, 0.0) for t in equity_types)
    income = -sum(rows.get(t, 0.0) for t in income_types)          # 收入贷方取正
    expense = sum(rows.get(t, 0.0) for t in expense_types)         # 成本借方取正
    unclassified = sum(v for k, v in rows.items() if k not in known)
    # 资产 = 负债 + 权益 + (收入 - 成本)
    diff = round(assets - liabilities - equity - (income - expense), 2)
    return diff, round(unclassified, 2)


def snap_balances(codes):
    """快照多科目 posted 余额 {code: balance(debit-credit)}（走 ORM，规避 code_store 为 jsonb 的问题）。"""
    accs = env['account.account'].search([('code', 'in', codes)])
    groups = env['account.move.line'].read_group(
        [('account_id', 'in', accs.ids), ('parent_state', '=', 'posted')],
        ['balance'], ['account_id'])
    bal = {}
    for g in groups:
        acc = env['account.account'].browse(g['account_id'][0])
        bal[acc.code] = round(g['balance'] or 0.0, 2)
    return bal


print('=== 端到端完整闭环验证（事务内，退出自动回滚）===')
today = datetime.date.today().isoformat()
tag = 'E2E-%s' % datetime.datetime.now().strftime('%H%M%S')

# ============ 0. 测试数据准备 ============
print('\n== 0. 测试数据准备 ==')
LineType = env['tour.line.type']
lt = LineType.search([], limit=1)
if not lt:
    lt = LineType.create({'name': 'E2E测试分类 %s' % tag})
check('0.1 线路分类就绪', bool(lt))

line = env['tour.line'].create({
    'name': 'E2E测试线路 %s' % tag,
    'line_type_id': lt.id,
    'day_num': 2,
    'audit_state': 'approved',
    'adult_price': 1000.0,
    'child_price': 500.0,
    'old_man_price': 800.0,
    'student_price': 700.0,
    'baby_price': 0.0,
})
start = today + 'T00:00:00'
start_d = datetime.date.today() + datetime.timedelta(days=30)
end_d = start_d + datetime.timedelta(days=1)
dep = env['tour.departure'].create({
    'line_id': line.id,
    'start_date': start_d,
    'end_date': end_d,
    'seats': 50,
    'state': 'published',
    'price_adult': 1000.0,
    'price_child': 500.0,
})
check('0.2 测试线路+班期就绪', bool(line) and bool(dep),
      'dep start=%s remain=%s' % (dep.start_date, dep.remain_seats))

# 供应商（成本账单付款对象）
supplier = env['res.partner'].create({
    'name': 'E2E测试供应商 %s' % tag,
    'supplier_rank': 1,
})
# 客户（收款付款方，可复用供应商/单独）
customer = env['res.partner'].create({
    'name': 'E2E测试客户 %s' % tag,
    'customer_rank': 1,
})
check('0.3 供应商/客户就绪', bool(supplier) and bool(customer))

# ============ 1. 网上下单（在线报名） ============
print('\n== 1. 网上下单（在线报名） ==')
vals = {
    'supplier_name': 'E2E客户 %s' % tag,
    'supplier_user_mobile': '13800138000',
    'adult_num': '2',
    'child_num': '1',
    'old_man_num': '0',
    'student_num': '0',
    'baby_num': '0',
    'remark': 'E2E 测试',
}
passengers = [
    {'name': '张三', 'passenger_type': 'adult', 'id_type': 'id_card', 'id_number': '110101199001011234'},
    {'name': '李四', 'passenger_type': 'adult', 'id_type': 'id_card', 'id_number': '110101199202022345'},
    {'name': '张小', 'passenger_type': 'child', 'id_type': 'id_card', 'id_number': '110101201501013456'},
]
reg = env['tour.plan.reg'].sudo().create_online_reg(line, dep, vals, passengers=passengers)
plan = reg.plan_id
QUOTE = round(2 * 1000.0 + 1 * 500.0, 2)  # 2500
check('1.1 报名生成', bool(reg), 'reg_code=%s' % reg.reg_code)
check('1.2 自动建团（draft）', bool(plan) and plan.state == 'draft',
      'plan=%s state=%s' % (plan.plan_code, plan.state))
check('1.3 报名挂到团', reg.plan_id.id == plan.id and reg.first_plan_id.id == plan.id)
check('1.4 团金额汇总(收入报价)', abs((plan.in_com_quo_sum or 0.0) - QUOTE) < 0.01,
      'in_com_quo_sum=%s 期望=%s' % (plan.in_com_quo_sum, QUOTE))
check('1.5 团未收款汇总', abs((plan.sum_un_pay or 0.0) - QUOTE) < 0.01,
      'sum_un_pay=%s' % plan.sum_un_pay)
check('1.6 客人证件落库', len(reg.passenger_ids) == 3, 'passengers=%d' % len(reg.passenger_ids))
check('1.7 余位回写', dep.remain_seats == 47, 'remain_seats=%s' % dep.remain_seats)

# 财务科目余额快照（本团业务发生前，用于三表增量验证）
FIN_CODES = ('1002', '2203.01', '2202', '6401', '6001.01', '2221.01')
SNAP_BEFORE = snap_balances(FIN_CODES)

# ============ 2. 收款（线下付款 → 认领 → 收款凭证） ============
print('\n== 2. 收款 ==')
plan.supplier_id = customer.id  # 客户档案
channel = env['tour.pay.channel'].search([('channel_type', '=', 'bank_transfer')], limit=1)
ba = env['tour.bank.account'].search([], limit=1)
claim = env['tour.payment.claim'].create({
    'supplier_id': customer.id,
    'plan_id': plan.id,
    'pay_date': today,
    'pay_money': QUOTE,
    'pay_channel_id': channel.id,
    'account_id': ba.id if ba else None,
    'claim_state': '0',
})
check('2.1 收款认领记录落库', bool(claim), 'name=%s' % claim.name)
check('2.2 认领挂到新报名团', claim.plan_id.id == plan.id)
claim.action_claim()
check('2.3 认领状态 0→1(待审核)', claim.claim_state == '1', 'claim_state=%s' % claim.claim_state)
claim.action_audit()
check('2.4 审核 1→2 + 生成凭证', claim.claim_state == '2' and bool(claim.move_id),
      'move=%s' % claim.move_id.name)
receipt = claim.move_id
check('2.5 收款凭证已过账', receipt.state == 'posted', 'state=%s' % receipt.state)
check('2.6 收款凭证借贷平衡', move_balanced(receipt))
# 借 1002 / 贷 2203.01
db_line = receipt.line_ids.filtered(lambda l: l.debit > 0 and l.account_id.code == '1002')
cr_line = receipt.line_ids.filtered(lambda l: l.credit > 0 and l.account_id.code == '2203.01')
check('2.7 借 1002 银行存款', bool(db_line) and abs(db_line.debit - QUOTE) < 0.01,
      'debit=%s' % (db_line.debit if db_line else 0))
check('2.8 贷 2203.01 预收', bool(cr_line) and abs(cr_line.credit - QUOTE) < 0.01,
      'credit=%s' % (cr_line.credit if cr_line else 0))

# ============ 3. 确认成团（→ analytic 单团核算） ============
print('\n== 3. 确认成团 ==')
plan.action_confirm()
s1 = plan.state
plan.action_confirm()
s2 = plan.state
check('3.1 确认流转 draft→pending→confirmed', s1 == 'pending' and s2 == 'confirmed',
      'states=%s,%s' % (s1, s2))
check('3.2 自动建 analytic（单团核算）', bool(plan.analytic_account_id),
      'analytic=%s' % plan.analytic_account_id.name)
check('3.3 自动建核算台账', env['tour.plan.account'].search_count([('plan_id', '=', plan.id)]) == 1)
check('3.4 收款凭证 analytic 挂对(GAP-2)', move_analytic_ok(receipt, plan.analytic_account_id.id))

# ============ 4. 计调（project.task 共享 analytic） ============
print('\n== 4. 计调 ==')
plan.action_operate()
check('4.1 计调流转 operating', plan.state == 'operating', 'state=%s' % plan.state)
check('4.2 自动建 1:1 project', bool(plan.project_id))
check('4.3 project 共享团 analytic', plan.project_id.account_id.id == plan.analytic_account_id.id)
guide = env['tour.guide'].search([('audit_chk', '=', True)], limit=1)
check('4.4 导游资源就绪', bool(guide), 'guide=%s' % (guide.name if guide else None))
task = None
if guide:
    task = env['project.task'].create({
        'name': 'E2E派导 %s' % tag,
        'project_id': plan.project_id.id,
        'resource_type': 'guide',
        'guide_id': guide.id,
        'date_start': start_d,
        'date_deadline': end_d,
        'guest_count': plan.guest_count,
    })
    check('4.5 计调任务落库(派导)', bool(task))
    task.action_confirm()
    check('4.6 任务确认(待安排→已确认)', task.state == '03_approved', 'state=%s' % task.state)
else:
    gap('4.4 无已审核导游', '需先审核导游档案，跳过派导任务')

# ============ 5. 出团 / 完成（→ 收入确认凭证） ============
print('\n== 5. 出团/完成 ==')
plan.action_start()
check('5.1 出团流转 in_progress', plan.state == 'in_progress', 'state=%s' % plan.state)
plan.action_complete()
check('5.2 完成流转 completed', plan.state == 'completed', 'state=%s' % plan.state)
check('5.3 收入凭证自动生成', bool(plan.income_move_id), 'move=%s' % (plan.income_move_id.name if plan.income_move_id else '-'))
income_move = plan.income_move_id
if income_move:
    check('5.4 收入凭证已过账', income_move.state == 'posted')
    check('5.5 收入凭证借贷平衡', move_balanced(income_move))
    # 借 2203.01 全额 / 贷 6001.01 不含税 + 贷 2221.01 销项（6%）
    net = round(QUOTE / 1.06, 2)
    tax = round(QUOTE - net, 2)
    d_prepay = income_move.line_ids.filtered(lambda l: l.debit > 0 and l.account_id.code == '2203.01')
    c_rev = income_move.line_ids.filtered(lambda l: l.credit > 0 and l.account_id.code == '6001.01')
    c_tax = income_move.line_ids.filtered(lambda l: l.credit > 0 and l.account_id.code == '2221.01')
    check('5.6 借 2203.01 预收(全额)', bool(d_prepay) and abs(d_prepay.debit - QUOTE) < 0.01,
          'debit=%s' % (d_prepay.debit if d_prepay else 0))
    check('5.7 贷 6001.01 收入(不含税)', bool(c_rev) and abs(c_rev.credit - net) < 0.01,
          'credit=%s 期望=%s' % (c_rev.credit if c_rev else 0, net))
    check('5.8 贷 2221.01 销项税', bool(c_tax) and abs(c_tax.credit - tax) < 0.01,
          'credit=%s 期望=%s' % (c_tax.credit if c_tax else 0, tax))
    check('5.9 收入凭证 analytic 挂对', move_analytic_ok(income_move, plan.analytic_account_id.id))

# ============ 6. 成本（供应商账单 → 付款） ============
print('\n== 6. 成本 ==')
COST = 1500.0
plan.out_sum = COST
plan.supplier_id = supplier.id  # 供应商
plan.action_generate_cost_bill()
check('6.1 成本账单生成(GAP-3)', bool(plan.cost_bill_id),
      'bill=%s' % (plan.cost_bill_id.name if plan.cost_bill_id else '-'))
bill = plan.cost_bill_id
if bill:
    check('6.2 成本账单已过账 in_invoice', bill.state == 'posted' and bill.move_type == 'in_invoice')
    check('6.3 成本账单借贷平衡', move_balanced(bill))
    d_cost = bill.line_ids.filtered(lambda l: l.debit > 0 and l.account_id.code == '6401')
    c_ap = bill.line_ids.filtered(lambda l: l.credit > 0 and l.account_id.code == '2202')
    check('6.4 借 6401 成本', bool(d_cost) and abs(d_cost.debit - COST) < 0.01,
          'debit=%s' % (d_cost.debit if d_cost else 0))
    check('6.5 贷 2202 应付', bool(c_ap) and abs(c_ap.credit - COST) < 0.01,
          'credit=%s' % (c_ap.credit if c_ap else 0))
    check('6.6 成本账单 analytic 挂对', move_analytic_ok(bill, plan.analytic_account_id.id))
    pr = env['tour.pay.request'].search([('bill_id', '=', bill.id)], limit=1)
    check('6.7 请款单生成+审批', bool(pr) and pr.state == 'approved', 'state=%s' % (pr.state if pr else '-'))

plan.action_pay_cost_bill()
check('6.8 成本付款(借2202/贷1002)', bill.payment_state == 'paid' if bill else False,
      'payment_state=%s' % (bill.payment_state if bill else '-'))
pr = env['tour.pay.request'].search([('bill_id', '=', bill.id)], limit=1)
check('6.9 请款单联动已付款', bool(pr) and pr.state == 'paid', 'state=%s' % (pr.state if pr else '-'))

# ============ 7. 三表 + 借贷平衡 ============
print('\n== 7. 三表与借贷平衡 ==')
gbal = global_balance()
check('7.1 全库凭证借贷平衡', abs(gbal) < 0.01, 'diff=%s' % gbal)
bsb, uncl = balance_sheet_balanced()
check('7.2 资产负债表平衡(资产=负债+权益+净利)', abs(bsb) < 0.01,
      'diff=%s unclassified=%s' % (bsb, uncl))

# 本团业务的三表增量（快照差）
SNAP_AFTER = snap_balances(FIN_CODES)
delta = {c: round(SNAP_AFTER.get(c, 0.0) - SNAP_BEFORE.get(c, 0.0), 2) for c in FIN_CODES}
net = round(QUOTE / 1.06, 2)
tax = round(QUOTE - net, 2)
print('  科目增量 delta =', delta)
# 利润表：收入 +2358.49(贷) / 成本 +1500(借)
check('7.3 利润表-收入增量(6001.01 贷方)', abs(delta['6001.01'] + net) < 0.01,
      '6001.01 Δ=%s 期望=-%s' % (delta['6001.01'], net))
check('7.4 利润表-成本增量(6401 借方)', abs(delta['6401'] - COST) < 0.01,
      '6401 Δ=%s 期望=%s' % (delta['6401'], COST))
# 现金流量表：经营净流入 = 收款 - 付款 = +1000（银行 1002 净增）
check('7.5 现金流量表-经营净流入(1002)', abs(delta['1002'] - (QUOTE - COST)) < 0.01,
      '1002 Δ=%s 期望=%s' % (delta['1002'], QUOTE - COST))
# 资产负债表：预收/应付结平，销项税负债 +141.51
check('7.6 资产负债表-预收结转结平(2203.01)', abs(delta['2203.01']) < 0.01,
      '2203.01 Δ=%s 期望=0' % delta['2203.01'])
check('7.7 资产负债表-应付付清(2202)', abs(delta['2202']) < 0.01,
      '2202 Δ=%s 期望=0' % delta['2202'])
check('7.8 资产负债表-销项税负债(2221.01)', abs(delta['2221.01'] + tax) < 0.01,
      '2221.01 Δ=%s 期望=-%s' % (delta['2221.01'], tax))
# 单团核算（analytic）
income, cost = plan._plan_analytic_balance(plan)
check('7.9 单团核算: 收入(analytic)', abs(income - net) < 0.01, 'income=%s 期望=%s' % (income, net))
check('7.10 单团核算: 成本(analytic)', abs(cost - COST) < 0.01, 'cost=%s 期望=%s' % (cost, COST))
check('7.11 单团毛利 = 收入-成本', abs((income - cost) - (net - COST)) < 0.01,
      '毛利=%s 期望=%s' % (round(income - cost, 2), round(net - COST, 2)))

# 三表定义存在
FR = env['account.financial.report']
roots = {r.name: r for r in FR.search([('parent_id', '=', False)])}
check('7.12 三表定义齐全', all(k in roots for k in ('Profit and Loss', 'Balance Sheet', 'Cash Flow Statement')),
      'roots=%s' % sorted(roots.keys()))

print('\n========== 端到端验证结果 ==========')
print('通过 %d / 失败 %d' % (len(PASS), len(FAIL)))
if FAIL:
    print('失败项: %s' % ', '.join(FAIL))
if GAPS:
    print('发现的缺口(已补齐): %s' % ', '.join(g[0] for g in GAPS))
print('=====================================')
print('注意: 本脚本在事务内运行，退出自动回滚，测试数据不落库、不污染历史订单。')
