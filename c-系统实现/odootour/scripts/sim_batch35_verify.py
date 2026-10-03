# -*- coding: utf-8 -*-
"""批3.5 仿真验收核对（只读）：对 sim_batch35.py 落库结果做口径断言与取证。

运行方式同 sim_batch35.py（odoo shell stdin）。全程无写操作。
"""
from odoo import fields

DEP = env['ta.departure'].browse(92519)
O1 = env['ta.order'].browse(434855)
SIM = '仿真|批3.5'
O2 = env['ta.order'].search([('departure_id', '=', DEP.id), ('note', '=', SIM + '|O2')], limit=1)
O3 = env['ta.order'].search([('departure_id', '=', DEP.id), ('note', '=', SIM + '|O3')], limit=1)
P_GUIDE = env['res.partner'].search([('name', '=', '仿真|导游-林海')], limit=1)

print('=' * 72)
print('== 批3.5 仿真验收核对（只读）')
print('=' * 72)

# ---- 1 订单 ----
print('\n[1] 订单')
for tag, o in (('O1', O1), ('O2', O2), ('O3', O3)):
    kinds = {}
    for l in o.line_ids:
        kinds[l.kind] = kinds.get(l.kind, 0) + 1
    print(f'  {tag} {o.name}: state={o.state} 人数={o.heads} 价别={kinds} '
          f'总额={o.amount_total:.0f} 已付={o.amount_paid:.0f}')

# ---- 2 计调与账单付款 ----
print('\n[2] 计调条目 × 账单 × 付款')
tot_paid = 0.0
for it in env['ta.dispatch.item'].search(
        [('departure_id', '=', DEP.id), ('note', '=', SIM)], order='id'):
    bill = it.move_id
    paid = round(bill.amount_total - bill.amount_residual, 2) if bill else 0.0
    tot_paid += paid
    print(f'  {it.kind:8s} {it.name}: 金额={it.amount:.0f} bill_state={it.bill_state} '
          f'已付={paid:.0f} paid_date={it.paid_date or "-"} '
          f'(账单 {bill.name if bill else "-"} state={bill.state if bill else "-"} '
          f'pay_state={bill.payment_state if bill else "-"})')
print(f'  Σ已付={tot_paid:.0f}（预期 3960 = 1200+1760+1000+0）')

# ---- 3 收款闭环 ----
print('\n[3] 收款闭环（银行流水 × 认领单）')
for bl in env['ta.bank.line'].search([('ref', 'like', '仿真|网银-%')], order='id'):
    cl = env['ta.payment.claim'].search([('line_ids.bank_line_id', '=', bl.id)], limit=1)
    print(f'  {bl.ref}: {bl.amount:.0f} state={bl.state} 已认领={bl.claimed_amount:.0f} '
          f'登记人={bl.registered_by.name} | 认领 {cl.name} state={cl.state} '
          f'凭证={cl.move_id.name if cl.move_id else "-"} 审核人={cl.approved_by.name if cl.approved_by else "-"}')
for p in O1.plan_ids:
    print(f'  O1 期次「{p.name}」due={p.due_date} {p.amount_paid:.0f}/{p.amount:.0f}')

# ---- 4 导游三件套 ----
print('\n[4] 导游借支 / 报账 / 佣金')
loan = env['ta.guide.loan'].search([('note', '=', SIM)], limit=1)
gexp = env['ta.guide.expense'].search([('note', '=', SIM)], limit=1)
com = env['ta.guide.commission'].search([('note', '=', SIM)], limit=1)
print(f'  借支 {loan.name}: state={loan.state} 金额={loan.amount:.0f} '
      f'已冲抵={loan.deducted_amount:.0f} 未结清={loan.outstanding:.0f} '
      f'发放凭证={loan.paid_move_id.name if loan.paid_move_id else "-"}')
print(f'  报账 #{gexp.id}: state={gexp.state} 合计={gexp.amount_total:.0f} '
      f'审核人={gexp.approved_by.name if gexp.approved_by else "-"}')
print(f'  佣金 {com.name}: state={com.state} 补贴={com.allowance:.0f} '
      f'税后净额={com.net_amount:.0f} 冲抵={com.deducted_total:.0f} '
      f'余额支付={com.payable_rest:.0f}')
for d in com.deduct_line_ids:
    print(f'    冲抵行: 借款 {d.loan_id.name} 冲 {d.net_deduct:.0f}')

# ---- 5 费用报销 + 资产 ----
print('\n[5] 费用报销 × 固定资产')
exp = env['ta.expense'].search([('reason', '=', '仿真|门市采购宣传物料')], limit=1)
print(f'  报销 {exp.name}: state={exp.state} 金额={exp.amount:.0f} '
      f'凭证={exp.move_id.name if exp.move_id else "-"} '
      f'move_state={exp.move_id.state if exp.move_id else "-"}')
ast = env['ta.asset'].search([('note', '=', SIM)], limit=1)
deprec = env['ta.asset.depreciation'].search([('asset_id', '=', ast.id)], limit=1)
print(f'  资产 {ast.code}「{ast.name}」: state={ast.state} 原值={ast.cost:.0f} '
      f'月折旧={ast.monthly_depreciation:.2f} 累计={ast.accumulated_depreciation:.2f} '
      f'净值={ast.book_value:.2f}')
print(f'  折旧 2026-09: {deprec.amount:.2f} 凭证={deprec.move_id.name} '
      f'state={deprec.move_id.state}')

# ---- 6 四个视图口径 ----
print('\n[6] SQL 视图口径（本团 BQ00266）')
pnl = env['ta.team.pnl'].search([('departure_id', '=', DEP.id)], limit=1)
print(f'  单团损益: 已收款={pnl.income:.0f} 订单总额={pnl.order_total:.0f} '
      f'成本={pnl.cost_total:.0f} 成本净额={pnl.cost_net:.0f} '
      f'毛利(BS-19)={pnl.profit:.0f} 毛利(含税)={pnl.profit_tax_incl:.0f}')
print(f'    [锚] income=8200 order_total=16800 cost=5360；'
      f'BS-19 口径成本净额=计调5360+导游报账600=5960 → 毛利=2240（ta_guide M4 覆盖 compute）')
pay_rows = env['ta.supplier.payable'].search([('departure_id', '=', DEP.id)])
tot_open = 0.0
for r in pay_rows:
    tot_open += r.open_amount
    print(f'  应付({r.supplier_id.name}): 类别={r.kinds} 条目额={r.item_total:.0f} '
          f'账单面额={r.bill_total:.0f} 已付={r.paid_total:.0f} 未付={r.open_amount:.0f} '
          f'账单状态={r.bill_state}')
print(f'    [锚] Σ已付=3960 Σ未付=1400（实测 Σ未付={tot_open:.0f}）')
aging = env['ta.receivable.aging'].search(
    [('order_id', 'in', [O1.id, O2.id, O3.id])], order='order_id')
print(f'  应收账龄（3 单样本）:')
for a in aging:
    print(f'    {a.order_id.name}: bucket={a.bucket} 逾期天数={a.days_overdue} '
          f'应收余额={a.amount_open:.0f}')
perf = env['ta.guide.performance'].search([('guide_id', '=', P_GUIDE.id)])
print(f'  导游绩效（{P_GUIDE.name}）:')
for g in perf:
    print(f'    {g.ym}: 带团={g.tour_count} 人数={g.heads} 收入={g.income:.0f} '
          f'成本={g.cost_total:.0f} 毛利={g.profit:.0f} 报账={g.expense_count} '
          f'佣金净额={g.commission_net:.0f} 借支未结清={g.loan_outstanding:.0f}')

# ---- 7 总账不变量 ----
print('\n[7] 总账不变量（2026-10-01 起；行数=凭证行，非凭证数）')
env.cr.execute("""
    SELECT m.state, count(*),
           round(sum(l.debit)::numeric, 2), round(sum(l.credit)::numeric, 2)
    FROM account_move m JOIN account_move_line l ON l.move_id = m.id
    WHERE m.date >= '2026-10-01'
    GROUP BY m.state ORDER BY m.state
""")
for state, cnt, deb, cred in env.cr.fetchall():
    print(f'  state={state}: {cnt} 行 Σ借={deb} Σ贷={cred} 差={round(deb - cred, 2)}')
env.cr.execute("""
    SELECT m.state, count(DISTINCT m.id) FROM account_move m
    WHERE m.date >= '2026-10-01' GROUP BY m.state ORDER BY m.state
""")
rows = env.cr.fetchall()
print(f'  凭证数（10-01 起）: {rows}')
env.cr.execute("""
    SELECT count(*), round(sum(debit)::numeric,2), round(sum(credit)::numeric,2)
    FROM account_move_line l JOIN account_move m ON m.id = l.move_id
    WHERE m.state = 'posted'
""")
cnt, deb, cred = env.cr.fetchone()
print(f'  全库已过账: {cnt} 行 Σ借={deb} Σ贷={cred} 差={round(deb - cred, 2)}（必须=0）')

# ---- 8 占位与计数 ----
print('\n[8] 计数快照')
print(f'  seats_used={DEP.seats_used}/20（预期 12）')
env.cr.execute("SELECT count(*) FROM account_move")
print(f'  全库 account_move={env.cr.fetchone()[0]}（基线 406 + 新增 12 = 418）')

print('\n== 核对完成（只读，无写入） ==')
