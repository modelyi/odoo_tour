# -*- coding: utf-8 -*-
"""E2E 场景0d：可售班期/线路价/资源（只读）"""

def hdr(t):
    print('\n===== %s =====' % t)

hdr('published 未来班期 + 线路产品价（list_price via product_template）')
env.cr.execute("""
SELECT d.id, d.name, d.line_id, l.name AS line_name, pt.list_price, l.child_price,
       d.start_date, d.end_date, d.seats, d.booked_seats, d.price_adult, d.price_child,
       pt.is_published
FROM tour_departure d
JOIN tour_line l ON l.id = d.line_id
JOIN product_template pt ON pt.id = l.product_tmpl_id
WHERE d.state='published' AND d.start_date >= CURRENT_DATE
  AND (pt.list_price > 0 OR d.price_adult > 0)
ORDER BY d.start_date LIMIT 10""")
rows = env.cr.fetchall()
print('  条数=%d' % len(rows))
for r in rows:
    print('  ', r)

hdr('published 未来班期总数 / 线路产品已发布数')
env.cr.execute("SELECT count(*) FROM tour_departure WHERE state='published' AND start_date >= CURRENT_DATE")
print('  班期 =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM tour_line l JOIN product_template pt ON pt.id=l.product_tmpl_id WHERE pt.is_published")
print('  已发布线路 =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM tour_line l JOIN product_template pt ON pt.id=l.product_tmpl_id WHERE pt.list_price > 0")
print('  有价线路 =', env.cr.fetchone()[0])
env.cr.execute("""SELECT l.id, l.name, pt.list_price, l.child_price, l.old_man_price, l.student_price,
  l.baby_price, l.guide_share_rate, l.guide_premium, pt.is_published, l.audit_state
FROM tour_line l JOIN product_template pt ON pt.id=l.product_tmpl_id
WHERE pt.list_price > 0 ORDER BY l.id LIMIT 10""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('候选团明细（真实，未确认收入，含 reg）')
env.cr.execute("""
SELECT p.id, p.plan_code, p.plan_name, p.state, p.biz_mode, p.plan_type, p.guest_count,
  p.in_com_quo_sum, p.out_sum, p.sum_pay_normal, p.sum_un_pay, p.un_invoice_money,
  p.analytic_account_id, p.supplier_id, p.line_id, p.begin_date, p.end_date, p.first_plan_id
FROM tour_plan p
WHERE p.income_move_id IS NULL AND p.cost_bill_id IS NULL
  AND p.in_com_quo_sum > 0 AND p.out_sum > 0 AND p.supplier_id IS NOT NULL
  AND EXISTS (SELECT 1 FROM tour_plan_reg r WHERE r.plan_id=p.id)
  AND p.biz_mode = '12'
ORDER BY p.id DESC LIMIT 8""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('团 88809 / 88788 的报名明细')
for pid in (88809, 88791, 88788, 88789):
    env.cr.execute("""SELECT r.id, r.reg_code, r.plan_id, r.first_plan_id, r.biz_mode, r.from_type,
      r.guest_count, r.adult_num, r.child_num, r.in_com_quo_sum, r.sum_un_pay, r.sum_pay_normal,
      r.supplier_id, r.supplier_name FROM tour_plan_reg r WHERE r.plan_id=%s""", (pid,))
    print('  plan %s:' % pid, env.cr.fetchall())

hdr('团 88809 / 88788 的团头信息')
env.cr.execute("""SELECT id, plan_code, plan_name, line_id, biz_mode, begin_date, end_date,
  guest_count, adult_num, child_num, in_com_quo_sum, out_sum, sum_un_pay, supplier_id,
  supplier_name, analytic_account_id, state FROM tour_plan WHERE id IN (88809,88791,88788,88789)""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('既有已确认收入的真实团凭证（验证既有闭环科目）')
env.cr.execute("""
SELECT m.id, m.name, m.move_type, m.state, m.date, p.plan_code,
  (SELECT string_agg(a.code_store::text || ':' || round(l.debit,2) || '/' || round(l.credit,2), ' | ')
   FROM account_move_line l JOIN account_account a ON a.id=l.account_id
   WHERE l.move_id=m.id) AS lines_text
FROM tour_plan p JOIN account_move m ON m.id=p.income_move_id
WHERE p.id IN (88776, 88762, 88759) ORDER BY p.id DESC""")
for r in env.cr.fetchall():
    print('  ', r)

print('\n[DONE]')
