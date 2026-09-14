# -*- coding: utf-8 -*-
"""E2E 场景0g：资源与科目余额（只读）"""

def hdr(t):
    print('\n===== %s =====' % t)

hdr('已审核导游 + 员工（真实）')
env.cr.execute("""SELECT g.id, g.name, g.employee_id, e.name, e.employment_type
FROM tour_guide g JOIN hr_employee e ON e.id = g.employee_id
WHERE g.audit_chk AND g.employee_id IS NOT NULL ORDER BY g.id LIMIT 5""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('线路分成比例（导游分成来源）')
env.cr.execute("SELECT id, name, guide_share_rate, guide_premium FROM tour_line WHERE guide_share_rate > 0 LIMIT 6")
print('  有分成比例线路:', env.cr.fetchall())
env.cr.execute("SELECT count(*) FROM tour_line WHERE guide_share_rate > 0")
print('  数量 =', env.cr.fetchone()[0])

hdr('真实购物店（sup_type=shop）')
env.cr.execute("SELECT id, name->>'en_US' FROM res_partner WHERE sup_type='shop' ORDER BY id LIMIT 6")
for r in env.cr.fetchall():
    print('  ', r)

hdr('真实车辆（已审核）')
env.cr.execute("SELECT id, name, licence, seat_num FROM tour_vehicle WHERE audit_chk ORDER BY seat_num DESC NULLS LAST LIMIT 5")
for r in env.cr.fetchall():
    print('  ', r)

hdr('酒店/餐厅/景区供应商')
env.cr.execute("""SELECT id, name->>'en_US', sup_type FROM res_partner
WHERE sup_type IN ('hotel','meal','scenic') ORDER BY sup_type, id LIMIT 9""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('分析账户唯一性 + 台账')
env.cr.execute("""SELECT count(*) FROM (SELECT tour_plan_id FROM account_analytic_account
  WHERE tour_plan_id IS NOT NULL GROUP BY tour_plan_id HAVING count(*) > 1) t""")
print('  重复 tour_plan_id 的 analytic 数 =', env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM tour_plan_account WHERE plan_id IN (88788,88789,88791)")
print('  候选团已有台账数 =', env.cr.fetchone()[0])

hdr('余额：关键科目（posted）')
for c in ('1002', '2203.01', '6001.01', '6001.02', '6401', '2221.01', '2241.02',
          '2221.05', '6401.07', '2221.03'):
    a = env['account.account'].search([('code', '=', c)], limit=1)
    if not a:
        print('  %-9s 缺失' % c)
        continue
    env.cr.execute("SELECT COALESCE(SUM(debit)-SUM(credit),0) FROM account_move_line "
                   "WHERE account_id=%s AND parent_state='posted'", (a.id,))
    print('  %-9s id=%-4s 余额(借-贷)=%s' % (c, a.id, round(env.cr.fetchone()[0] or 0.0, 2)))

hdr('候选团 analytic 现有分析行')
for pid in (88788, 88789, 88791):
    aa = env['tour.plan'].browse(pid).analytic_account_id
    env.cr.execute("SELECT count(*), COALESCE(SUM(amount),0) FROM account_analytic_line WHERE account_id=%s", (aa.id,))
    print('  %s analytic %s 行数/合计 = %s' % (pid, aa.id, env.cr.fetchone()))

hdr('候选团成本账单明细（科目/analytic）')
for pid in (88788, 88789):
    p = env['tour.plan'].browse(pid)
    b = p.cost_bill_id
    print('  plan %s bill %s state=%s total=%s payment=%s partner=%s' % (
        p.plan_code, b.name, b.state, b.amount_total, b.payment_state, b.partner_id.name))
    for l in b.line_ids:
        print('      %-10s %-22s D=%-10s C=%-10s analytic=%s' % (
            l.account_id.code, l.account_id.name, l.debit, l.credit, l.analytic_distribution))

hdr('候选团是否已有收款')
env.cr.execute("SELECT count(*) FROM tour_payment_claim WHERE plan_id IN (88788,88789,88791)")
print('  claim 数 =', env.cr.fetchone()[0])

print('\n[DONE]')
