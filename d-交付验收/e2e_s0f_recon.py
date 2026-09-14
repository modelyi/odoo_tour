# -*- coding: utf-8 -*-
"""E2E 场景0f：锁定真实测试数据（只读）"""

def hdr(t):
    print('\n===== %s =====' % t)

hdr('真实客户档案（用于报名/收款方）')
env.cr.execute("""SELECT id, name->>'en_US', customer_rank, supplier_rank, sup_type FROM res_partner
WHERE customer_rank > 0 AND (name->>'en_US') NOT LIKE '%*%' ORDER BY id DESC LIMIT 8""")
for r in env.cr.fetchall():
    print('  ', r)

hdr('场景候选团（真实存量，金额自洽）')
for pid in (88788, 88789, 88791):
    p = env['tour.plan'].browse(pid)
    print('  plan %s | %s | %s | biz=%s type=%s | guest=%s' % (p.id, p.plan_code, p.plan_name, p.biz_mode, p.plan_type, p.guest_count))
    print('     报价=%s 成本=%s 已收=%s 未收=%s 分析=%s(id=%s) 客户=%s(id=%s) 线路=%s(id=%s)' % (
        p.in_com_quo_sum, p.out_sum, p.sum_pay_normal, p.sum_un_pay,
        p.analytic_account_id.name, p.analytic_account_id.id,
        p.supplier_id.name, p.supplier_id.id, p.line_id.name, p.line_id.id))
    print('     状态=%s 收入凭证=%s 成本账单=%s 发票缺口=%s' % (
        p.state, p.income_move_id.name or '-', p.cost_bill_id.name or '-', p.un_invoice_money))
    for r in env['tour.plan.reg'].search([('plan_id', '=', pid)]):
        print('     reg %s %s 报价=%s 未收=%s 已收=%s 客人=%s first_plan=%s' % (
            r.id, r.reg_code, r.in_com_quo_sum, r.sum_un_pay, r.sum_pay_normal,
            r.supplier_name, r.first_plan_id.id))

hdr('已审核导游 + 员工（真实）')
env.cr.execute("""SELECT g.id, g.name, g.employee_id, e.name->>'en_US' AS emp, e.employment_type
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
env.cr.execute("SELECT id, name->>'en_US', licence, seat_num FROM tour_vehicle WHERE audit_chk ORDER BY seat_num DESC LIMIT 5")
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

hdr('团 88788 的 analytic 现有分析行')
aa = env['tour.plan'].browse(88788).analytic_account_id
env.cr.execute("SELECT count(*), COALESCE(SUM(amount),0) FROM account_analytic_line WHERE account_id=%s", (aa.id,))
print('  88788 analytic 行数/合计 =', env.cr.fetchone())
aa2 = env['tour.plan'].browse(88789).analytic_account_id
env.cr.execute("SELECT count(*), COALESCE(SUM(amount),0) FROM account_analytic_line WHERE account_id=%s", (aa2.id,))
print('  88789 analytic 行数/合计 =', env.cr.fetchone())

print('\n[DONE]')
