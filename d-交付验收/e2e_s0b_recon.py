# -*- coding: utf-8 -*-
"""E2E 场景0b：科目表 / analytic / 候选团 精查（只读）"""

def hdr(t):
    print('\n===== %s =====' % t)

Acc = env['account.account']
hdr('关键科目（ORM 按 code 查）')
codes = ['1001', '1002', '1012', '1122.01', '1221.01', '2202', '2203', '2203.01',
         '2221.01', '2221.03', '2221.05', '2221.07', '2241.02', '2241.06',
         '6001.01', '6001.02', '6001.03', '6401', '6401.02', '6401.03', '6401.04',
         '6401.05', '6401.06', '6401.07', '6401.11', '6603']
for c in codes:
    a = Acc.search([('code', '=', c)], limit=1)
    if a:
        print('  %-9s id=%-5s type=%-22s 差额可扣=%s 名=%s' % (
            c, a.id, a.account_type, a.tour_vat_deductible, a.name))
    else:
        print('  %-9s **缺失**' % c)

hdr('所有标记 tour_vat_deductible=True 的科目')
res = Acc.search([('tour_vat_deductible', '=', True)])
print('  数量=%d' % len(res))
for a in res:
    print('    %-10s %s' % (a.code, a.name))

hdr('analytic account / line 规模')
env.cr.execute("SELECT count(*) FROM account_analytic_account")
print('  analytic account =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM account_analytic_account WHERE tour_plan_id IS NOT NULL")
print('  带 tour_plan_id =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM account_analytic_line")
print('  analytic line =', env.cr.fetchone()[0])
env.cr.execute("SELECT plan_id FROM account_analytic_plan")
print('  analytic plan ids =', env.cr.fetchall())

hdr('tour.plan.account 台账规模')
env.cr.execute("SELECT count(*), count(analytic_account_id) FROM tour_plan_account")
print('  total/hasAnalytic =', env.cr.fetchone())

hdr('候选团 A：state=pending 有完整金额+客户+线路+含报名，未确认收入未生成成本账单')
env.cr.execute("""
SELECT p.id, p.plan_code, p.plan_name, p.state, p.biz_mode, p.plan_type, p.guest_count,
       p.in_com_quo_sum, p.out_sum, p.un_invoice_money,
       p.analytic_account_id, p.supplier_id, p.line_id, p.begin_date, p.end_date,
       (SELECT count(*) FROM tour_plan_reg r WHERE r.plan_id = p.id) regs
FROM tour_plan p
WHERE p.state = 'pending' AND p.in_com_quo_sum > 0 AND p.out_sum > 0
  AND p.supplier_id IS NOT NULL AND p.income_move_id IS NULL AND p.cost_bill_id IS NULL
ORDER BY p.id DESC LIMIT 10""")
rows = env.cr.fetchall()
for r in rows:
    print('  ', r)

hdr('候选团 B：state=confirmed 未生成收入凭证（可走 收入确认）')
env.cr.execute("""
SELECT count(*) FROM tour_plan
WHERE state='confirmed' AND in_com_quo_sum>0 AND out_sum>0
  AND supplier_id IS NOT NULL AND income_move_id IS NULL""")
print('  confirmed 未确认收入 =', env.cr.fetchone()[0])

hdr('候选团 C：有 reg 且未确认收入的团')
env.cr.execute("""
SELECT p.id, p.plan_code, p.state, p.biz_mode, p.in_com_quo_sum, p.out_sum,
       p.analytic_account_id, p.supplier_id,
       (SELECT count(*) FROM tour_plan_reg r WHERE r.plan_id=p.id) regs,
       (SELECT count(*) FROM tour_plan_reg r WHERE r.plan_id=p.id AND r.in_com_quo_sum>0) regs_with_quote
FROM tour_plan p
WHERE p.income_move_id IS NULL AND p.in_com_quo_sum>0 AND p.out_sum>0 AND p.supplier_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM tour_plan_reg r WHERE r.plan_id=p.id)
ORDER BY regs DESC, p.id DESC LIMIT 10""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('tour.plan 的 biz_mode 分布（全量与未确认收入）')
env.cr.execute("SELECT biz_mode, count(*) FROM tour_plan GROUP BY biz_mode ORDER BY 2 DESC LIMIT 12")
print('  全量:', env.cr.fetchall())
env.cr.execute("""SELECT biz_mode, count(*) FROM tour_plan WHERE income_move_id IS NULL
 GROUP BY biz_mode ORDER BY 2 DESC LIMIT 12""")
print('  未确认收入:', env.cr.fetchall())

hdr('已有 income_move / cost_bill 的样本团（可验证既有闭环）')
env.cr.execute("""
SELECT p.id, p.plan_code, p.state, p.in_com_quo_sum, p.out_sum,
       p.income_move_id, m.state, m.name,
       p.cost_bill_id, b.state, b.name
FROM tour_plan p
LEFT JOIN account_move m ON m.id = p.income_move_id
LEFT JOIN account_move b ON b.id = p.cost_bill_id
WHERE p.income_move_id IS NOT NULL AND p.cost_bill_id IS NOT NULL
ORDER BY p.id DESC LIMIT 5""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('tour.departure 可售班期样本（真实线路）')
env.cr.execute("""
SELECT d.id, d.name, d.line_id, d.start_date, d.end_date, d.seats, d.booked_seats,
       d.price_adult, d.price_child, d.price_old_man, d.price_student, d.price_baby, d.state
FROM tour_departure d
WHERE d.state='published' AND d.start_date >= CURRENT_DATE
ORDER BY d.start_date LIMIT 5""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('product 化：tour.line → product.template')
env.cr.execute("SELECT count(*) FROM tour_line")
print('  tour.line =', env.cr.fetchone()[0])
env.cr.execute("""SELECT id, name, code, day_num, list_price, child_price, old_man_price,
    student_price, baby_price, audit_state FROM tour_line
    WHERE list_price > 0 ORDER BY id DESC LIMIT 5""")
for r in env.cr.fetchall():
    print('  ', r)
env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tour_line' AND column_name IN ('product_tmpl_id','list_price','adult_price','child_price','old_man_price','student_price','baby_price','audit_state')")
print('  tour_line 价格/产品列 =', env.cr.fetchall())

hdr('sale_order 现状')
env.cr.execute("SELECT id, name, state, partner_id, amount_total, date_order FROM sale_order ORDER BY id")
for r in env.cr.fetchall():
    print('  ', r)

print('\n[DONE]')
