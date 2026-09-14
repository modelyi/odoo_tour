# -*- coding: utf-8 -*-
"""E2E 场景0e：锁定真实测试数据（只读）"""

def hdr(t):
    print('\n===== %s =====' % t)

hdr('班期 11631 / 线路 663')
d = env['tour.departure'].browse(11631)
print('  dep:', d.id, d.name, 'line', d.line_id.id, d.line_id.name,
      'state', d.state, 'start', d.start_date, 'end', d.end_date)
print('  seats', d.seats, 'booked', d.booked_seats, 'remain', d.remain_seats)
print('  prices:', d.get_online_prices())

hdr('published 且 remain_seats>0 的未来班期（可真实报名）')
env.cr.execute("""
SELECT d.id, d.name, d.line_id, l.name, pt.list_price, d.start_date, d.seats, d.booked_seats,
       (d.seats - d.booked_seats) AS remain, d.price_adult, pt.is_published
FROM tour_departure d JOIN tour_line l ON l.id=d.line_id
JOIN product_template pt ON pt.id=l.product_tmpl_id
WHERE d.state='published' AND d.start_date >= CURRENT_DATE AND (d.seats - d.booked_seats) > 0
ORDER BY (d.seats-d.booked_seats) DESC LIMIT 10""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('真实客户档案（用于报名/收款方）')
env.cr.execute("""SELECT id, name, customer_rank, supplier_rank, sup_type FROM res_partner
WHERE customer_rank > 0 AND name NOT LIKE '%*%' AND name IS NOT NULL
ORDER BY id DESC LIMIT 8""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('场景候选团（真实存量，金额自洽）')
for pid in (88788, 88789, 88791):
    p = env['tour.plan'].browse(pid)
    print('  plan %s | %s | %s | biz=%s type=%s | guest=%s' % (p.id, p.plan_code, p.plan_name, p.biz_mode, p.plan_type, p.guest_count))
    print('     报价=%s 成本=%s 已收=%s 未收=%s 分析=%s(=%s) 客户=%s(%s) 线路=%s(%s)' % (
        p.in_com_quo_sum, p.out_sum, p.sum_pay_normal, p.sum_un_pay,
        p.analytic_account_id.name, p.analytic_account_id.id,
        p.supplier_id.name, p.supplier_id.id, p.line_id.name, p.line_id.id))
    print('     状态=%s 收入凭证=%s 成本账单=%s 发票缺口=%s' % (p.state, p.income_move_id.name or '-', p.cost_bill_id.name or '-', p.un_invoice_money))
    for r in env['tour.plan.reg'].search([('plan_id', '=', pid)]):
        print('     reg %s %s 报价=%s 未收=%s 已收=%s 客人=%s' % (r.id, r.reg_code, r.in_com_quo_sum, r.sum_un_pay, r.sum_pay_normal, r.supplier_name))

hdr('已审核导游（真实，带员工）')
env.cr.execute("""SELECT g.id, g.name, g.employee_id, g.partner_id, l.guide_share_rate
FROM tour_guide g LEFT JOIN tour_line l ON l.id = g.id
WHERE g.audit_chk LIMIT 5""")
for r in env.cr.fetchall():
    print('  ', r)
env.cr.execute("""SELECT g.id, g.name, g.employee_id, e.name AS emp_name, e.employment_type
FROM tour_guide g JOIN hr_employee e ON e.id = g.employee_id
WHERE g.audit_chk AND g.employee_id IS NOT NULL LIMIT 5""")
for r in env.cr.fetchall():
    print('  guide+emp', r)
# 导游分成比例来源：线路 guide_share_rate（非 0 的）
env.cr.execute("SELECT id, name, guide_share_rate, guide_premium FROM tour_line WHERE guide_share_rate > 0 LIMIT 5")
print('  线路有分成比例:', env.cr.fetchall())

hdr('真实购物店（sup_type=shop）')
env.cr.execute("SELECT id, name, sup_type FROM res_partner WHERE sup_type='shop' ORDER BY id LIMIT 6")
for r in env.cr.fetchall():
    print('  ', r)

hdr('真实车辆（已审核）')
env.cr.execute("SELECT id, name, licence, seat_num FROM tour_vehicle WHERE audit_chk ORDER BY seat_num DESC LIMIT 5")
for r in env.cr.fetchall():
    print('  ', r)

hdr('酒店/餐厅/景区供应商')
env.cr.execute("""SELECT id, name, sup_type FROM res_partner WHERE sup_type IN ('hotel','meal','scenic')
ORDER BY sup_type, id LIMIT 9""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('分析账户唯一约束核对')
env.cr.execute("""SELECT count(*) FROM (
  SELECT tour_plan_id FROM account_analytic_account WHERE tour_plan_id IS NOT NULL
  GROUP BY tour_plan_id HAVING count(*) > 1) t""")
print('  重复 tour_plan_id 的 analytic 数 =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM tour_plan_account WHERE plan_id IN (88788,88789,88791)")
print('  候选团已有台账数 =', env.cr.fetchone()[0])

hdr('余额：关键科目（posted）')
for c in ('1002', '2203.01', '6001.01', '6001.02', '6401', '2221.01', '2241.02', '2221.05', '6401.07', '2221.03'):
    a = env['account.account'].search([('code', '=', c)], limit=1)
    if not a:
        print('  %-9s 缺失' % c)
        continue
    env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line WHERE account_id=%s AND parent_state='posted'", (a.id,))
    print('  %-9s 余额(借-贷)=%s' % (c, round(env.cr.fetchone()[0] or 0.0, 2)))

print('\n[DONE]')
