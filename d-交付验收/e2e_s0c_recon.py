# -*- coding: utf-8 -*-
"""E2E 场景0c：analytic / 候选团 / 资源（只读）"""

def hdr(t):
    print('\n===== %s =====' % t)

hdr('analytic plan')
for p in env['account.analytic.plan'].search([]):
    print('  id=%s name=%s' % (p.id, p.name))

hdr('tour.plan.account 台账规模')
env.cr.execute("SELECT count(*), count(analytic_account_id) FROM tour_plan_account")
print('  total/hasAnalytic =', env.cr.fetchone())

hdr('候选团 A：pending，金额完整+客户+线路，未确认收入未生成成本账单')
env.cr.execute("""
SELECT p.id, p.plan_code, p.plan_name, p.state, p.biz_mode, p.plan_type, p.guest_count,
       p.in_com_quo_sum, p.out_sum, p.un_invoice_money,
       p.analytic_account_id, p.supplier_id, p.line_id, p.begin_date, p.end_date,
       (SELECT count(*) FROM tour_plan_reg r WHERE r.plan_id = p.id) regs
FROM tour_plan p
WHERE p.state = 'pending' AND p.in_com_quo_sum > 0 AND p.out_sum > 0
  AND p.supplier_id IS NOT NULL AND p.income_move_id IS NULL AND p.cost_bill_id IS NULL
ORDER BY p.id DESC LIMIT 8""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('候选团 C：有 reg 且未确认收入的团（全状态）')
env.cr.execute("""
SELECT p.id, p.plan_code, p.plan_name, p.state, p.biz_mode, p.in_com_quo_sum, p.out_sum,
       p.supplier_id, p.analytic_account_id,
       (SELECT count(*) FROM tour_plan_reg r WHERE r.plan_id=p.id) regs
FROM tour_plan p
WHERE p.income_move_id IS NULL AND p.in_com_quo_sum>0 AND p.out_sum>0 AND p.supplier_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM tour_plan_reg r WHERE r.plan_id=p.id)
ORDER BY regs DESC, p.id DESC LIMIT 8""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('biz_mode 分布')
env.cr.execute("SELECT biz_mode, count(*) FROM tour_plan WHERE income_move_id IS NULL GROUP BY biz_mode ORDER BY 2 DESC LIMIT 10")
print('  未确认收入:', env.cr.fetchall())

hdr('既有闭环样本（income_move+cost_bill 都有）')
env.cr.execute("""
SELECT p.id, p.plan_code, p.state, p.in_com_quo_sum, p.out_sum,
       p.income_move_id, m.state, m.name, p.cost_bill_id, b.state, b.name
FROM tour_plan p
LEFT JOIN account_move m ON m.id = p.income_move_id
LEFT JOIN account_move b ON b.id = p.cost_bill_id
WHERE p.income_move_id IS NOT NULL AND p.cost_bill_id IS NOT NULL
ORDER BY p.id DESC LIMIT 4""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('tour.departure 可售班期（真实线路，有价）')
env.cr.execute("""
SELECT d.id, d.name, d.line_id, d.start_date, d.end_date, d.seats, d.booked_seats,
       d.price_adult, d.price_child, d.price_old_man, d.price_student, d.price_baby, d.state
FROM tour_departure d
WHERE d.state='published' AND d.start_date >= CURRENT_DATE AND d.price_adult > 0
  AND d.line_id IS NOT NULL
ORDER BY d.start_date LIMIT 5""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('tour_line 列 & 价格样本')
env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tour_line'")
cols = [r[0] for r in env.cr.fetchall()]
print('  含 product_tmpl_id:', 'product_tmpl_id' in cols)
print('  含 list_price:', 'list_price' in cols)
env.cr.execute("SELECT id, name, code, day_num, list_price, child_price, old_man_price, student_price, baby_price, audit_state FROM tour_line WHERE list_price > 0 ORDER BY id DESC LIMIT 5")
for r in env.cr.fetchall():
    print('  ', r)

hdr('line → product 回链')
env.cr.execute("SELECT count(*) FROM tour_line WHERE product_tmpl_id IS NOT NULL")
print('  tour_line 有 product_tmpl_id =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM product_template")
print('  product_template =', env.cr.fetchone()[0])

hdr('sale_order 现状')
env.cr.execute("SELECT id, name, state, partner_id, amount_total, date_order FROM sale_order ORDER BY id")
for r in env.cr.fetchall():
    print('  ', r)

hdr('客户/供应商真实样本')
env.cr.execute("SELECT id, name, customer_rank, supplier_rank, sup_type FROM res_partner WHERE customer_rank>0 AND name !~ '\\*' ORDER BY id DESC LIMIT 5")
for r in env.cr.fetchall():
    print('  cust  ', r)
env.cr.execute("SELECT id, name, sup_type FROM res_partner WHERE sup_type='hotel' ORDER BY id LIMIT 3")
for r in env.cr.fetchall():
    print('  hotel ', r)
env.cr.execute("SELECT id, name, sup_type FROM res_partner WHERE sup_type='meal' ORDER BY id LIMIT 2")
for r in env.cr.fetchall():
    print('  meal  ', r)
env.cr.execute("SELECT id, name, sup_type FROM res_partner WHERE sup_type='scenic' ORDER BY id LIMIT 2")
for r in env.cr.fetchall():
    print('  scenic', r)
env.cr.execute("SELECT id, name, sup_type FROM res_partner WHERE sup_type='vehicle_comp' ORDER BY id LIMIT 2")
for r in env.cr.fetchall():
    print('  vehicle', r)
env.cr.execute("SELECT id, name, sup_type FROM res_partner WHERE sup_type='shop' ORDER BY id LIMIT 3")
for r in env.cr.fetchall():
    print('  shop  ', r)

hdr('导游/车辆真实样本（已审核）')
env.cr.execute("SELECT id, name, employee_id, partner_id FROM tour_guide WHERE audit_chk ORDER BY id LIMIT 5")
for r in env.cr.fetchall():
    print('  guide ', r)
env.cr.execute("SELECT id, name, licence, seat_num FROM tour_vehicle WHERE audit_chk ORDER BY id LIMIT 5")
for r in env.cr.fetchall():
    print('  vehicle ', r)

hdr('hr.employee 用工类型分布（佣金个税类型）')
env.cr.execute("SELECT employment_type, count(*) FROM hr_employee GROUP BY employment_type")
print('  ', env.cr.fetchall())

print('\n[DONE]')
